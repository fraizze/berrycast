"""Service AirPlay (« Recopie de l'écran » iPhone/iPad/Mac) : python3 -m berrycast.airplay.service

UxPlay (paquet Debian « uxplay », 1.71 sur Debian 13) est utilisé tel quel. Ce service :
- le lance avec le nom de l'appareil, l'écran HDMI (kmssink), le son (HDMI/jack) ;
- active le code PIN Apple (« -pin nnnn », depuis UxPlay 1.67) : la 1re fois, l'iPhone
  demande un code à 4 chiffres ; il est affiché EN GRAND sur la TV ;
- suit l'état (connexion, diffusion) pour l'écran, via les connexions TCP actives :
  avec l'option « -p », UxPlay utilise les ports fixes 7000 (contrôle) et 7100 (vidéo) ;
- l'arrête pendant une diffusion Windows (une seule diffusion à la fois), puis le relance.

Le code PIN est fixe pour cet appareil (tiré au hasard une fois, gardé dans
$STATE_DIRECTORY/pin) : l'iPhone ne le demande qu'à la première connexion.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from berrycast import audio, cast_state, config
from berrycast.miracast.pipeline import (
    DEFAULT_DISPLAY,
    VIDEO_SINK,
    choose_decoder,
    display_size,
)

log = logging.getLogger("berrycast.airplay")

SOURCE = "airplay"
STATE_DIR = Path(os.environ.get("STATE_DIRECTORY", "/var/lib/berrycast-airplay"))
CONTROL_PORT = 7000  # « -p » : ports TCP 7100, 7000, 7001
MIRROR_PORT = 7100
PIN_SHOW_SECONDS = 90
# Dessin du code par UxPlay (police FIGlet « colossal ») : uniquement ces caractères
PIN_ART = re.compile(r"^[ 8dbPYo\".]+$")


def load_pin(state_dir: Path = STATE_DIR) -> str:
    """Code PIN AirPlay de cet appareil (créé au premier lancement)."""
    path = state_dir / "pin"
    try:
        pin = path.read_text().strip()
        if re.fullmatch(r"\d{4}", pin) and pin != "0000":
            return pin
    except OSError:
        pass
    pin = f"{secrets.randbelow(9999) + 1:04d}"  # 0001 à 9999 (UxPlay refuse 0000)
    state_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(pin + "\n")
    os.chmod(path, 0o600)
    return pin


# Format le plus allongé d'un iPhone tenu en paysage (19,5:9 = 2,17), avec une marge
WIDEST_ASPECT = 2.2


def requested_size(display: tuple[int, int]) -> tuple[int, int]:
    """Taille demandée à l'iPhone (option -s d'UxPlay).

    Doc d'UxPlay : c'est la HAUTEUR qui règle la taille du flux ; la largeur suit la forme
    de l'image. Constaté sur le Pi : en paysage, avec la hauteur 1080, l'image faisait
    ~2340 de large, plus que l'écran (1920) et que le décodeur : la diffusion plantait.
    On demande donc une hauteur telle que l'image en paysage tienne dans la largeur.
    """
    width, height = display
    h = min(height, int(width / WIDEST_ASPECT))
    return width, h - h % 2


def build_command(device_name: str, pin: str, alsa_device: str | None,
                  decoder: str, display: tuple[int, int] = DEFAULT_DISPLAY) -> list[str]:
    """Arguments d'UxPlay (liste : pas de shell)."""
    # stdbuf : UxPlay écrit ses messages tout de suite (sinon ils restent en mémoire et
    # arrivent par paquets, jusqu'à plusieurs minutes plus tard : constaté sur le Pi)
    cmd = ["stdbuf", "-oL", "-eL", "uxplay", "-n", device_name, "-nh", "-pin", pin, "-p",
           "-vs", os.environ.get("BERRYCAST_VIDEO_SINK", VIDEO_SINK),
           # Constaté sur le Pi : avec la synchronisation par horodatage (défaut), UxPlay
           # rejetait toutes les images (« invalid ntp_time < gst_video_pipeline_base_time ») :
           # on affiche les images dès leur arrivée (doc UxPlay : « -vsync no »).
           "-vsync", "no",
           "-s", "{}x{}".format(*requested_size(display))]
    if alsa_device:
        cmd += ["-as", f"alsasink device={alsa_device}"]
    if decoder == "avdec_h264":
        cmd.append("-avdec")  # Pi 5 / pas de décodeur matériel
    else:
        # Constaté sur le Pi : forte latence. UxPlay convertit l'image avec « videoconvert »
        # (processeur) : sur Raspberry Pi, sa doc conseille le décodeur et le convertisseur
        # matériels (v4l2h264dec, v4l2convert). -bt709 : nécessaire avec le décodeur matériel.
        cmd += ["-vd", "v4l2h264dec", "-vc", "v4l2convert", "-bt709"]
    return cmd


def established_ports(tcp_text: str) -> set[int]:
    """Ports LOCAUX des connexions TCP établies (contenu de /proc/net/tcp ou tcp6)."""
    ports = set()
    for line in tcp_text.splitlines()[1:]:
        fields = line.split()
        if len(fields) > 3 and fields[3] == "01":  # 01 = ESTABLISHED
            try:
                ports.add(int(fields[1].rsplit(":", 1)[1], 16))
            except (IndexError, ValueError):
                continue
    return ports


def current_ports() -> set[int]:
    ports: set[int] = set()
    for name in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            ports |= established_ports(Path(name).read_text())
        except OSError:
            pass
    return ports


def is_pin_art(line: str) -> bool:
    """Ligne du dessin du code PIN affiché par UxPlay (au moins quelques « 8 »)."""
    text = line.rstrip("\n")
    return len(text) >= 20 and text.count("8") >= 3 and bool(PIN_ART.match(text))


def decide_state(ports: set[int], pin_shown_at: float | None, now: float) -> str:
    if MIRROR_PORT in ports:
        return "casting"
    if pin_shown_at is not None and now - pin_shown_at < PIN_SHOW_SECONDS:
        return "pin"
    if CONTROL_PORT in ports:
        return "connecting"
    return "ready"


class AirPlayService:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.process: subprocess.Popen | None = None
        self.pin_shown_at: float | None = None
        self.peer = ""

    def read_output(self, stream) -> None:
        """Lit les messages d'UxPlay : dessin du code PIN, nom de l'appareil qui se connecte."""
        for raw in stream:
            line = raw.decode(errors="replace").rstrip()
            if is_pin_art(line):
                if self.pin_shown_at is None or time.monotonic() - self.pin_shown_at > 5:
                    log.info("L'iPhone demande le code PIN")
                self.pin_shown_at = time.monotonic()
                continue  # inutile de recopier le dessin dans le journal
            m = re.search(r"connection request from (.+?) \(", line)
            if m:
                self.peer = m.group(1)
            if line:
                log.info("uxplay: %s", line)

    def start(self, cfg) -> None:
        cmd = build_command(cfg.device_name, load_pin(), audio.alsa_device(cfg.audio_output),
                            choose_decoder(), display_size())
        pin_index = cmd.index("-pin") + 1
        log.info("Lancement : %s", " ".join("****" if i == pin_index else a
                                            for i, a in enumerate(cmd)))
        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        start_new_session=True)
        threading.Thread(target=self.read_output, args=(self.process.stdout,),
                         daemon=True).start()

    def stop_uxplay(self) -> None:
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()
        self.process = None

    def run(self) -> int:
        cfg = config.load()
        if not cfg.airplay_enabled:
            cast_state.write(SOURCE, "off")
            log.info("AirPlay désactivé dans la configuration")
            self.stop_event.wait()
            return 0
        pin = load_pin()
        try:
            while not self.stop_event.is_set():
                # Windows prépare ou fait une diffusion : on libère l'écran (UxPlay le garde
                # dès son démarrage, même sans iPhone connecté)
                if cast_state.other_wants_screen(SOURCE):
                    if self.process:
                        log.info("Diffusion Windows : AirPlay mis en pause (écran libéré)")
                        self.stop_uxplay()
                    cast_state.write(SOURCE, "off", pin=pin)
                    self.stop_event.wait(0.5)
                    continue
                if self.process is None or self.process.poll() is not None:
                    if self.process is not None:
                        log.warning("UxPlay s'est arrêté (code %s) : relance",
                                    self.process.returncode)
                        self.stop_event.wait(2)
                    self.start(cfg)
                state = decide_state(current_ports(), self.pin_shown_at, time.monotonic())
                if state == "casting":
                    self.pin_shown_at = None
                cast_state.write(SOURCE, state, pin=pin, peer=self.peer)
                self.stop_event.wait(1)
        finally:
            self.stop_uxplay()
            cast_state.write(SOURCE, "off")
        return 0

    def stop(self, *_args) -> None:
        self.stop_event.set()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    service = AirPlayService()
    signal.signal(signal.SIGTERM, service.stop)
    signal.signal(signal.SIGINT, service.stop)
    return service.run()


if __name__ == "__main__":
    sys.exit(main())
