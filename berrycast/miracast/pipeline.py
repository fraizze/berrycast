"""Lecteur vidéo Miracast : GStreamer (gst-launch-1.0), plein écran sur l'HDMI sans bureau.

Flux reçu : RTP (UDP 1028) contenant du MPEG-TS, avec vidéo H.264 et son AAC.
  udpsrc -> rtpjitterbuffer -> rtpmp2tdepay -> tsdemux
     vidéo : h264parse -> décodeur -> kmssink (écran HDMI, via KMS/DRM)
     son   : aacparse -> avdec_aac -> alsasink (HDMI ou jack)

Décodeur : matériel « v4l2h264dec » si le Pi en a un (Pi 3, 4, Zero 2 W : /dev/video10
du pilote bcm2835-codec), sinon logiciel « avdec_h264 » (Pi 5 : pas de décodeur H.264).

La chaîne vidéo est la même que celle d'UxPlay, qui fonctionne sur le Pi 3 (constaté) :
  h264parse ! v4l2h264dec ! v4l2convert ! videoscale ! kmssink can-scale=false
"""

from __future__ import annotations

import logging
import os
import shlex
import signal
import subprocess
from pathlib import Path

from berrycast import audio
from berrycast.miracast import wfd

log = logging.getLogger("berrycast.miracast.pipeline")

HW_DECODER_DEVICE = Path("/dev/video10")  # décodeur H.264 matériel (bcm2835-codec)
# can-scale=false : constaté sur le Pi 3, kmssink échoue en agrandissant l'image
# (« drmModeSetPlane failed: No space left on device ») : image affichée à sa taille réelle.
VIDEO_SINK = "kmssink sync=false can-scale=false"
DRM_DIR = Path("/sys/class/drm")
DEFAULT_DISPLAY = (1920, 1080)
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


def video_chain(decoder: str) -> str:
    """Décodage + conversion, comme UxPlay : matériel (v4l2) ou logiciel (Pi 5)."""
    if decoder == "v4l2h264dec":
        return "v4l2h264dec ! v4l2convert ! videoscale"
    return "avdec_h264 ! videoconvert ! videoscale"


def build_command(decoder: str, alsa_device: str | None, port: int = wfd.RTP_PORT,
                  video_sink: str | None = None) -> list[str]:
    """Arguments de gst-launch-1.0 (liste : pas de shell, pas d'injection possible)."""
    sink = video_sink or os.environ.get("BERRYCAST_VIDEO_SINK", VIDEO_SINK)
    audio_sink = "alsasink sync=false" + (f" device={alsa_device}" if alsa_device else "")
    description = (
        f"udpsrc port={port} buffer-size=2097152 "
        "caps=\"application/x-rtp,media=video,clock-rate=90000,encoding-name=MP2T\" "
        f"! rtpjitterbuffer latency={JITTER_LATENCY_MS} ! rtpmp2tdepay "
        "! tsdemux name=demux "
        f"demux. ! queue max-size-time=0 max-size-buffers=0 ! h264parse "
        f"! {video_chain(decoder)} ! {sink} "
        "demux. ! queue max-size-time=0 max-size-buffers=0 ! aacparse ! avdec_aac "
        f"! audioconvert ! audioresample ! {audio_sink}"
    )
    return ["gst-launch-1.0", "-q", "-e"] + shlex.split(description)


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
        cmd = build_command(decoder, audio.alsa_device(self.audio_output))
        log.info("Lecteur : %s", " ".join(cmd))
        # Nouveau groupe de processus : on pourra tout arrêter d'un coup
        # GST_DEBUG=2 : erreurs et avertissements de GStreamer dans le journal (diagnostic)
        env = dict(os.environ, GST_DEBUG=os.environ.get("GST_DEBUG", "2"))
        self.process = subprocess.Popen(cmd, start_new_session=True, env=env)

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
