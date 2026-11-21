"""Lecteur vidéo Miracast : GStreamer (gst-launch-1.0), plein écran sur l'HDMI sans bureau.

Flux reçu : RTP (UDP 1028) contenant du MPEG-TS, avec vidéo H.264 et son AAC.
  udpsrc -> rtpjitterbuffer -> rtpmp2tdepay -> tsdemux
     vidéo : h264parse -> décodeur -> kmssink (écran HDMI, via KMS/DRM)
     son   : aacparse -> avdec_aac -> alsasink (HDMI ou jack)

Décodeur : matériel « v4l2h264dec » si le Pi en a un (Pi 3, 4, Zero 2 W : /dev/video10
du pilote bcm2835-codec), sinon logiciel « avdec_h264 » (Pi 5 : pas de décodeur H.264).

Mise à la taille de l'écran par la puce (« v4l2convert », /dev/video12) et non par le
processeur. Constaté sur le Pi 3 : avec « videoscale » (processeur), chaque image 1080p
était recalculée (kmssink can-scale=false n'accepte que la taille ET la forme de pixel
exactes de l'écran, calculée d'après ses dimensions physiques) : trop lent, les images
s'accumulaient (~20 s de retard). v4l2convert sait produire exactement ce format.
  h264parse ! v4l2h264dec ! queue (perte des images en trop) ! v4l2convert ! kmssink
"""

from __future__ import annotations

import logging
import os
import shlex
import signal
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from berrycast import audio
from berrycast.miracast import wfd

log = logging.getLogger("berrycast.miracast.pipeline")

HW_DECODER_DEVICE = Path("/dev/video10")  # décodeur H.264 matériel (bcm2835-codec)
HW_CONVERTER_DEVICE = Path("/dev/video12")  # conversion / mise à l'échelle matérielle (ISP)
# Garde-fou : si l'affichage prend du retard, on saute des images décodées au lieu de les
# empiler (sinon le retard grandit sans fin). Ne jamais jeter les données AVANT le décodeur :
# une image manquante abîmerait toutes les suivantes.
DROP_LATE_FRAMES = "queue leaky=downstream max-size-buffers=2 max-size-bytes=0 max-size-time=0"
# can-scale=false : constaté sur le Pi 3, kmssink échoue en agrandissant l'image
# (« drmModeSetPlane failed: No space left on device ») : image affichée à sa taille réelle.
VIDEO_SINK = "kmssink sync=false can-scale=false"
DRM_DIR = Path("/sys/class/drm")
DEFAULT_DISPLAY = (1920, 1080)
# Tampon de réception UDP (limité par net.core.rmem_max : system/sysctl/90-berrycast.conf)
UDP_BUFFER_BYTES = 4 * 1024 * 1024
UDP_TABLES = (Path("/proc/net/udp"), Path("/proc/net/udp6"))
JITTER_LATENCY_MS = 150  # petit tampon : bon compromis fluidité / latence en Wi-Fi


def pi_model() -> str:
    try:
        return Path("/proc/device-tree/model").read_text(errors="replace").strip("\x00\n ")
    except OSError:
        return ""


def choose_decoder(model: str | None = None, hw_device_exists: bool | None = None) -> str:
    """« v4l2h264dec » (matériel) ou « avdec_h264 » (logiciel)."""
    model = pi_model() if model is None else model
    if hw_device_exists is None:
        hw_device_exists = HW_DECODER_DEVICE.exists()
    if "Raspberry Pi 5" in model or not hw_device_exists:
        return "avdec_h264"
    return "v4l2h264dec"


def decoder_for_profile(decoder: str, profile: int | None) -> str:
    """Le décodeur matériel du Pi refuse le profil « Constrained High » (constaté).

    On n'annonce que « Constrained Baseline » (0x01) ; si la source choisit malgré tout un
    autre profil (0x02 = Constrained High), on décode par le processeur : plus lent, mais
    une image vaut mieux qu'un écran noir.
    """
    if decoder == "v4l2h264dec" and profile is not None and not profile & 0x01:
        return "avdec_h264"
    return decoder


def parse_mode(text: str) -> tuple[int, int] | None:
    """Première ligne de /sys/class/drm/card0-HDMI-A-1/modes (« 1920x1080 ») -> (1920, 1080).

    Le premier mode de la liste est le mode préféré de l'écran, celui qu'utilise la console.
    """
    for line in text.splitlines():
        line = line.strip().split("i")[0]  # « 1920x1080i » (entrelacé) -> « 1920x1080 »
        if "x" in line:
            w, _, h = line.partition("x")
            if w.isdigit() and h.isdigit():
                return int(w), int(h)
    return None


def display_size(drm_dir: Path = DRM_DIR) -> tuple[int, int]:
    """Taille de l'écran HDMI branché (1920x1080 si inconnue)."""
    try:
        connectors = sorted(drm_dir.glob("card*-HDMI-A-*"))
    except OSError:
        return DEFAULT_DISPLAY
    for connector in connectors:
        try:
            if (connector / "status").read_text().strip() != "connected":
                continue
            mode = parse_mode((connector / "modes").read_text())
        except OSError:
            continue
        if mode:
            return mode
    return DEFAULT_DISPLAY


def udp_port_open(port: int, tables: list[str]) -> bool:
    """Le port UDP est-il ouvert sur le Pi ? (contenu de /proc/net/udp et udp6)

    Colonne 2 : « adresse:port » en hexadécimal, ex. « 00000000:0404 » = port 1028.
    """
    wanted = f"{port:04X}"
    for text in tables:
        for line in text.splitlines()[1:]:
            fields = line.split()
            if len(fields) > 1 and fields[1].rsplit(":", 1)[-1].upper() == wanted:
                return True
    return False


def read_udp_tables() -> list[str]:
    tables = []
    for path in UDP_TABLES:
        try:
            tables.append(path.read_text())
        except OSError:
            pass
    return tables


def has_hw_converter(model: str | None = None, device_exists: bool | None = None) -> bool:
    """Le Pi a-t-il le convertisseur matériel v4l2convert (Pi 3, 4, Zero 2 W) ?"""
    model = pi_model() if model is None else model
    if device_exists is None:
        device_exists = HW_CONVERTER_DEVICE.exists()
    return device_exists and "Raspberry Pi 5" not in model


def video_chain(decoder: str, hw_convert: bool = True) -> str:
    """Décodage puis mise au format de l'écran (par la puce si possible)."""
    convert = "v4l2convert" if hw_convert else "videoconvert ! videoscale"
    return f"{decoder} ! {DROP_LATE_FRAMES} ! {convert}"


def build_command(decoder: str, alsa_device: str | None, port: int = wfd.RTP_PORT,
                  video_sink: str | None = None, hw_convert: bool = True) -> list[str]:
    """Arguments de gst-launch-1.0 (liste : pas de shell, pas d'injection possible)."""
    sink = video_sink or os.environ.get("BERRYCAST_VIDEO_SINK", VIDEO_SINK)
    audio_sink = "alsasink sync=false" + (f" device={alsa_device}" if alsa_device else "")
    description = (
        f"udpsrc port={port} buffer-size={UDP_BUFFER_BYTES} "
        "caps=\"application/x-rtp,media=video,clock-rate=90000,encoding-name=MP2T\" "
        f"! rtpjitterbuffer latency={JITTER_LATENCY_MS} ! rtpmp2tdepay "
        "! tsdemux name=demux "
        f"demux. ! queue max-size-time=0 max-size-buffers=0 ! h264parse "
        f"! {video_chain(decoder, hw_convert)} ! {sink} "
        "demux. ! queue max-size-time=0 max-size-buffers=0 ! aacparse ! avdec_aac "
        f"! audioconvert ! audioresample ! {audio_sink}"
    )
    # -v : formats choisis entre chaque étape écrits dans le journal (taille, forme des
    # pixels, mémoire) : indispensable pour comprendre un écran noir ou un retard.
    return ["gst-launch-1.0", "-v", "-e"] + shlex.split(description)


class Player:
    """Lance / arrête le lecteur GStreamer (un seul à la fois)."""

    def __init__(self, audio_output: str = "hdmi"):
        self.audio_output = audio_output
        self.process: subprocess.Popen | None = None

    def start(self, profile: int | None = None, software: bool = False) -> None:
        """profile : profil H.264 choisi par la source (M4), pour choisir le décodeur.
        software : forcer le décodage par le processeur (secours si le matériel échoue)."""
        self.stop()
        decoder = "avdec_h264" if software else decoder_for_profile(choose_decoder(), profile)
        if profile is not None:
            log.info("Profil H.264 choisi par la source : 0x%02X -> décodeur %s", profile, decoder)
        cmd = build_command(decoder, audio.alsa_device(self.audio_output),
                            hw_convert=has_hw_converter())
        log.info("Lecteur : %s", " ".join(cmd))
        # Nouveau groupe de processus : on pourra tout arrêter d'un coup
        # GST_DEBUG=2 : erreurs et avertissements de GStreamer dans le journal (diagnostic)
        env = dict(os.environ, GST_DEBUG=os.environ.get("GST_DEBUG", "2"))
        self.process = subprocess.Popen(cmd, start_new_session=True, env=env)

    def wait_listening(self, port: int = wfd.RTP_PORT, timeout: float = 6.0,
                       read_tables: Callable[[], list[str]] = read_udp_tables,
                       clock: Callable[[], float] = time.monotonic,
                       sleep: Callable[[float], None] = time.sleep) -> bool:
        """Attend que le lecteur écoute sur le port de la vidéo.

        Constaté sur le Pi 3 : gst-launch met 1 à 2 s à démarrer. Si la source commence à
        envoyer avant, la première image complète (avec les réglages SPS/PPS) est perdue,
        et rien ne peut être décodé ensuite. Une fois le port ouvert, le système garde les
        paquets en attente même si le lecteur n'est pas tout à fait prêt.
        """
        deadline = clock() + timeout
        while clock() < deadline:
            if udp_port_open(port, read_tables()):
                return True
            if self.process is not None and self.process.poll() is not None:
                return False  # le lecteur s'est arrêté
            sleep(0.1)
        return False

    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGINT)  # -e : fin propre
                self.process.wait(timeout=3)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait()
        log.info("Lecteur arrêté (code %s)", self.process.returncode)
        self.process = None
