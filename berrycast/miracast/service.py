"""Service Miracast (Windows + K) : python3 -m berrycast.miracast.service

Miracast over Infrastructure (MS-MICE, voir mice.py) :
1. le Pi s'annonce en Wi-Fi Direct (écoute, sans groupe) avec la capacité MICE ;
2. le PC Windows (même réseau que le Pi) se connecte au port 7250 : SOURCE_READY ;
3. le Pi se connecte au RTSP du PC, négocie (M1–M7) et lance le lecteur vidéo.

Une seule diffusion à la fois : si l'iPhone diffuse déjà (AirPlay), la demande du PC est
refusée. Désactivé dans la configuration (miracast_enabled = false) : le service attend.
"""

from __future__ import annotations

import logging
import signal
import socket
import subprocess
import sys
import threading
import time

from berrycast import cast_state, config
from berrycast.miracast import wfd
from berrycast.miracast.mice import MiceServer
from berrycast.miracast.p2p import LISTEN_SECONDS, WifiDirect
from berrycast.miracast.pipeline import (
    Player,
    display_size,
    max_video_height,
    read_udp_tables,
    stream_size,
    udp_drops,
)
from berrycast.miracast.rtsp_sink import RtspSink
from berrycast.miracast.wfd import RTP_PORT

log = logging.getLogger("berrycast.miracast")

SOURCE = "miracast"
WIFI_IFACE = "wlan0"
LOOP_SECONDS = 10
REANNOUNCE_SECONDS = 300  # réannonce de toute façon toutes les 5 min


def parse_ipv4(ip_output: str) -> str | None:
    """Adresse IPv4 dans la sortie de « ip -4 -o addr show dev wlan0 »."""
    for line in ip_output.splitlines():
        parts = line.split()
        if "inet" in parts:
            return parts[parts.index("inet") + 1].split("/")[0]
    return None


def wifi_ipv4(iface: str = WIFI_IFACE) -> str | None:
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show", "dev", iface],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_ipv4(out)


class MiracastService:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.cfg = None
        self.session: RtspSink | None = None
        self.busy = False  # une projection est en cours de préparation ou de diffusion
        self.player: Player | None = None
        self.lock = threading.Lock()
        self.peer = ""

    # ---- Projection (appelé par le serveur MICE) --------------------------------------

    def on_ready(self, source_ip: str, rtsp_port: int, name: str) -> None:
        with self.lock:
            if self.busy:
                log.info("Une diffusion Windows est déjà en cours : %s refusé", source_ip)
                return
            if cast_state.other_is_casting(SOURCE):
                log.info("Un iPhone diffuse déjà : %s refusé", source_ip)
                return
            self.busy = True
        self.peer = name
        cast_state.write(SOURCE, "connecting", peer=name)
        threading.Thread(target=self.run_session, args=(source_ip, rtsp_port),
                         daemon=True).start()

    def on_stop(self) -> None:
        session = self.session
        if session is not None:
            session.stop()

    def run_session(self, source_ip: str, rtsp_port: int) -> None:
        try:
            self._run_session(source_ip, rtsp_port)
        except Exception:
            log.exception("Erreur pendant la diffusion")
        finally:
            if self.player:
                self.player.stop()
            self.session = None
            with self.lock:
                self.busy = False
            cast_state.write(SOURCE, "ready")

    def _run_session(self, source_ip: str, rtsp_port: int) -> None:
        log.info("Connexion au RTSP du PC %s:%s", source_ip, rtsp_port)
        sock = None
        for _ in range(10):  # le PC ouvre son RTSP juste après SOURCE_READY
            try:
                sock = socket.create_connection((source_ip, rtsp_port), timeout=3)
                break
            except OSError:
                time.sleep(0.5)
        if sock is None:
            log.warning("Le RTSP du PC ne répond pas")
            return
        self.player = Player(self.cfg.audio_output)
        playing = threading.Event()

        def on_play() -> None:
            if not cast_state.wait_screen_free(SOURCE):
                log.warning("AirPlay n'a pas libéré l'écran à temps : essai quand même")
            self.player.start(self.session.video_profile)
            self.wait_player()
            playing.set()
            cast_state.write(SOURCE, "casting", peer=self.peer)

        display = display_size()
        wanted = stream_size(display, max_video_height())
        log.info("Écran %dx%d, flux demandé jusqu'à %dx%d : modes proposés à Windows %s",
                 *display, *wanted, wfd.video_formats(wanted))
        self.session = RtspSink(sock, source_ip, self.cfg.device_name, on_play=on_play,
                                on_stop=self.player.stop, display=wanted)
        worker = threading.Thread(target=self.session.run, daemon=True)
        worker.start()
        crashes, drops_seen = 0, udp_drops(RTP_PORT, read_udp_tables())
        while worker.is_alive():
            worker.join(timeout=5)
            if self.stop_event.is_set():
                self.session.stop()
            elif playing.is_set() and worker.is_alive():
                cast_state.write(SOURCE, "casting", peer=self.peer)  # « toujours en cours »
                drops = udp_drops(RTP_PORT, read_udp_tables())
                if drops > drops_seen:
                    log.warning("Paquets vidéo perdus (tampon plein) : %d", drops - drops_seen)
                    drops_seen = drops
                if not self.player.running():
                    # Pas de passage au décodage logiciel ici : un arrêt peut venir du son,
                    # et le décodage par le processeur est bien trop lent sur un Pi 3.
                    crashes += 1
                    log.warning("Le lecteur s'est arrêté (%d fois) : relance", crashes)
                    self.player.start(self.session.video_profile)
                    self.wait_player()
                    self.session.schedule_idr()  # le nouveau lecteur a besoin d'une image complète
        log.info("Diffusion terminée : %s", self.session.reason)

    def wait_player(self) -> None:
        """Attend que le lecteur écoute avant que la vidéo parte (voir Player.wait_listening)."""
        start = time.monotonic()
        if self.player.wait_listening():
            log.info("Lecteur à l'écoute après %.1f s", time.monotonic() - start)
        else:
            log.warning("Le lecteur n'écoute pas encore sur le port vidéo : on continue")

    # ---- Boucle -----------------------------------------------------------------------

    def run(self) -> int:
        self.cfg = config.load()
        if not self.cfg.miracast_enabled:
            cast_state.write(SOURCE, "off")
            log.info("Miracast désactivé dans la configuration")
            self.stop_event.wait()
            return 0
        server = MiceServer(self.on_ready, self.on_stop)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        log.info("En attente de Windows + K (port MICE %s)", server.port)
        p2p = None
        hostname = socket.gethostname()
        announced_ip, last_announce, last_listen, last_error = None, 0.0, 0.0, ""
        try:
            while not self.stop_event.is_set():
                now = time.monotonic()
                try:
                    if p2p is None:
                        p2p = WifiDirect(WIFI_IFACE)
                    ip = wifi_ipv4() or ""
                    if ip != announced_ip or now - last_announce > REANNOUNCE_SECONDS:
                        p2p.announce(self.cfg.device_name, hostname, ip or None)
                        announced_ip, last_announce = ip, now
                    if now - last_listen > LISTEN_SECONDS - 2 * LOOP_SECONDS and not self.busy:
                        p2p.listen()
                        last_listen = now
                    if not self.busy:
                        cast_state.write(SOURCE, "ready" if ip else "off")
                    last_error = ""
                except Exception as exc:  # D-Bus / wpa_supplicant : on réessaie
                    message = f"{type(exc).__name__}: {exc}"
                    if message != last_error:
                        log.error("Wi-Fi Direct indisponible : %s (nouvel essai)", message)
                        last_error = message
                    p2p, announced_ip, last_listen = None, None, 0.0
                    if not self.busy:
                        cast_state.write(SOURCE, "off")
                self.stop_event.wait(LOOP_SECONDS)
        finally:
            server.close()
            self.on_stop()
            if self.player:
                self.player.stop()
            if p2p:
                p2p.clear_announce()
            cast_state.write(SOURCE, "off")
        return 0

    def stop(self, *_args) -> None:
        self.stop_event.set()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    service = MiracastService()
    signal.signal(signal.SIGTERM, service.stop)
    signal.signal(signal.SIGINT, service.stop)
    return service.run()


if __name__ == "__main__":
    sys.exit(main())
