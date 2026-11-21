"""Service Miracast (Windows + K) : python3 -m berrycast.miracast.service

Boucle principale :
1. annonce Wi-Fi Direct + groupe permanent + adresse 192.168.173.1 + serveur DHCP ;
2. code PIN à 8 chiffres affiché sur la TV (cast_state) et accepté par le groupe ;
3. dès que le PC est connecté (192.168.173.80), négociation RTSP puis lecteur vidéo ;
4. fin de diffusion : nouveau PIN, retour à l'attente.

Une seule diffusion à la fois : si l'iPhone diffuse déjà (AirPlay), la connexion du PC
est refusée (le PC affiche une erreur), puis tout redevient disponible.
Désactivé dans la configuration (miracast_enabled = false) : le service attend sans rien faire.
"""

from __future__ import annotations

import logging
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from berrycast import cast_state, config
from berrycast.miracast import wfd
from berrycast.miracast.p2p import P2PError, WifiDirect
from berrycast.miracast.pipeline import Player
from berrycast.miracast.rtsp_sink import RtspSink

log = logging.getLogger("berrycast.miracast")

SINK_IP = "192.168.173.1"
SOURCE_IP = "192.168.173.80"  # seule adresse distribuée par notre DHCP
LEASES = Path("/run/berrycast/miracast-dhcp.leases")
SOURCE = "miracast"


def dhcp_command(ifname: str, leases: Path = LEASES) -> list[str]:
    """dnsmasq en simple serveur DHCP (pas de DNS, pas de routeur) sur le groupe."""
    return [
        "dnsmasq", "--keep-in-foreground", "--conf-file=/dev/null", "--port=0",
        f"--interface={ifname}", "--bind-interfaces", "--except-interface=lo",
        f"--dhcp-range={SOURCE_IP},{SOURCE_IP},255.255.255.0,1h",
        "--dhcp-option=3", "--dhcp-option=6",  # ni passerelle ni DNS : Internet reste sur la box
        "--dhcp-authoritative", f"--dhcp-leasefile={leases}", "--pid-file=", "--log-dhcp",
    ]


class MiracastService:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.p2p: WifiDirect | None = None
        self.ifname = ""
        self.group_path: str | None = None
        self.dhcp: subprocess.Popen | None = None
        self.pin = ""
        self.session: RtspSink | None = None
        self.player: Player | None = None
        self.last_error = ""

    # ---- Réseau du groupe ---------------------------------------------------------

    def setup_network(self, ifname: str) -> None:
        if ifname == self.ifname and self.dhcp and self.dhcp.poll() is None:
            return
        self.stop_dhcp()
        subprocess.run(["ip", "addr", "replace", f"{SINK_IP}/24", "dev", ifname], check=True)
        subprocess.run(["ip", "link", "set", ifname, "up"], check=True)
        LEASES.parent.mkdir(parents=True, exist_ok=True)
        self.dhcp = subprocess.Popen(dhcp_command(ifname))
        self.ifname = ifname
        log.info("Réseau Wi-Fi Direct prêt sur %s (%s)", ifname, SINK_IP)

    def stop_dhcp(self) -> None:
        if self.dhcp and self.dhcp.poll() is None:
            self.dhcp.terminate()
            try:
                self.dhcp.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.dhcp.kill()
        self.dhcp = None

    def report_error(self, exc: Exception) -> None:
        """Journalise une erreur sans répéter 100 fois la même trace (elle revient toutes
        les 10 s tant que le problème dure)."""
        message = f"{type(exc).__name__}: {exc}"
        if message != self.last_error:
            log.error("Wi-Fi Direct indisponible : %s (nouvel essai toutes les 10 s)", message,
                      exc_info=not isinstance(exc, (P2PError, subprocess.CalledProcessError)))
            self.last_error = message

    def new_pin(self) -> None:
        self.pin = wfd.new_pin()
        self.p2p.allow_pin(self.pin, self.ifname)
        cast_state.write(SOURCE, "ready", pin=wfd.format_pin(self.pin))

    # ---- Session ----------------------------------------------------------------------

    def try_connect(self) -> socket.socket | None:
        try:
            return socket.create_connection((SOURCE_IP, wfd.RTSP_PORT), timeout=1.0)
        except OSError:
            return None

    def run_session(self, sock: socket.socket, device_name: str, audio_output: str) -> None:
        if cast_state.other_is_casting(SOURCE):
            log.info("Un iPhone diffuse déjà : connexion du PC refusée")
            sock.close()
            time.sleep(3)
            return
        cast_state.write(SOURCE, "connecting", pin=wfd.format_pin(self.pin))
        self.player = Player(audio_output)
        playing = threading.Event()

        def on_play() -> None:
            self.player.start()
            playing.set()
            cast_state.write(SOURCE, "casting")

        self.session = RtspSink(sock, SOURCE_IP, device_name, on_play=on_play,
                                on_stop=self.player.stop)
        worker = threading.Thread(target=self.session.run, daemon=True)
        worker.start()
        while worker.is_alive():
            worker.join(timeout=5)
            if self.stop_event.is_set():
                self.session.stop()
            elif playing.is_set():
                cast_state.write(SOURCE, "casting")  # « toujours en cours » pour l'écran
                if not self.player.running():
                    log.warning("Le lecteur s'est arrêté : relance")
                    self.player.start()
        self.player.stop()
        log.info("Session terminée : %s", self.session.reason)
        self.session = None

    # ---- Boucle -----------------------------------------------------------------------

    def run(self) -> int:
        cfg = config.load()
        if not cfg.miracast_enabled:
            cast_state.write(SOURCE, "off")
            log.info("Miracast désactivé dans la configuration")
            self.stop_event.wait()
            return 0
        self.p2p = WifiDirect()
        self.p2p.announce(cfg.device_name)
        try:
            while not self.stop_event.is_set():
                try:
                    group_path, ifname = self.p2p.ensure_group()
                    group_key = group_path or ifname
                    if group_key != self.group_path:
                        self.pin = ""  # nouveau groupe : il faut lui redonner le PIN
                        self.group_path = group_key
                    self.setup_network(ifname)
                    if not self.pin:
                        self.new_pin()
                except Exception as exc:  # P2P, D-Bus, réseau : on réessaie dans 10 s
                    self.report_error(exc)
                    cast_state.write(SOURCE, "off")
                    self.pin = ""
                    self.group_path = None
                    self.stop_event.wait(10)
                    continue
                self.last_error = ""

                sock = self.try_connect()
                if sock is None:
                    cast_state.write(SOURCE, "ready", pin=wfd.format_pin(self.pin))
                    self.stop_event.wait(1)
                    continue
                log.info("PC connecté : négociation Miracast")
                self.run_session(sock, cfg.device_name, cfg.audio_output)
                self.pin = ""  # le PIN a servi : on en tire un nouveau
        finally:
            if self.player:
                self.player.stop()
            self.stop_dhcp()
            self.p2p.clear_announce()
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
