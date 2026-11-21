"""Lecteur vidéo Miracast : GStreamer (gst-launch-1.0), plein écran sur l'HDMI sans bureau.

Flux reçu : RTP (UDP 1028) contenant du MPEG-TS, avec vidéo H.264 et son AAC.
  udpsrc -> rtpmp2tdepay -> tsdemux
     vidéo : h264parse -> décodeur -> kmssink (écran HDMI, via KMS/DRM)
     son   : aacparse -> avdec_aac -> alsasink (HDMI ou jack)

Décodeur : matériel « v4l2h264dec » si le Pi en a un (Pi 3, 4, Zero 2 W : /dev/video10
du pilote bcm2835-codec), sinon logiciel « avdec_h264 » (Pi 5 : pas de décodeur H.264).

Mise à la taille de l'écran par la puce (« v4l2convert », /dev/video12) et non par le
processeur. Constaté sur le Pi 3 : avec « videoscale » (processeur), chaque image 1080p
était recalculée (kmssink can-scale=false n'accepte que la taille ET la forme de pixel
exactes de l'écran, calculée d'après ses dimensions physiques) : trop lent, les images
s'accumulaient (~20 s de retard). v4l2convert sait produire exactement ce format.
  h264parse ! v4l2h264dec ! queue (perte des images en trop) ! v4l2convert
    ! capsfilter (taille exacte de l'écran) ! kmssink
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
# Son : format de sortie FIXE. Constaté sur le Pi : Windows envoie d'abord un son de
# format inattendu (4000 Hz, 1 canal), puis change de format quand une vidéo démarre ;
# la sortie son, renégociée en pleine diffusion, échouait (« Le format du flux n'est pas
# correct ») et arrêtait tout le lecteur. audioconvert/audioresample absorbent les
# changements, la sortie son garde toujours le même format.
AUDIO_OUT_CAPS = "audio/x-raw,format=S16LE,rate=48000,channels=2"
# Tampon de réception UDP (limité par net.core.rmem_max : system/sysctl/90-berrycast.conf)
UDP_BUFFER_BYTES = 4 * 1024 * 1024
UDP_TABLES = (Path("/proc/net/udp"), Path("/proc/net/udp6"))
# Pas de « rtpjitterbuffer » : constaté sur le Pi 3, couleurs qui bavent et gels même en
# 640x480. Le Wi-Fi du Pi livre les paquets par paquets groupés (économie d'énergie) ;
# rtpjitterbuffer jetait ceux arrivés plus de 150 ms après l'heure prévue, et l'image se
# corrompait jusqu'à la prochaine image complète. Sur une liaison Wi-Fi directe les paquets
# arrivent dans l'ordre : le réordonnancement est inutile (lazycast n'en a pas non plus).


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


def max_video_height(model: str | None = None) -> int:
    """Plus grande hauteur d'image à demander à Windows selon le modèle de Pi.

    Constaté sur le Pi 3 B : en 1080p, une vidéo plein écran sur le PC faisait saturer le
    Wi-Fi (2,4 GHz seulement) : gros retard et gels. En 720p, le débit est environ divisé
    par deux ; la puce agrandit ensuite l'image à la taille de l'écran (sans processeur).
    Pi 4 / Pi 5 (Wi-Fi 5 GHz, plus puissants) : 1080p.
    """
    model = pi_model() if model is None else model
    return 1080 if ("Raspberry Pi 4" in model or "Raspberry Pi 5" in model) else 720


def stream_size(display: tuple[int, int], max_height: int) -> tuple[int, int]:
    """Taille utilisée pour choisir les modes proposés à Windows (écran, plafonnée)."""
    width, height = display
    if height > max_height:
        return max_height * 16 // 9, max_height
    return width, height


def udp_drops(port: int, tables: list[str]) -> int:
    """Paquets UDP jetés par le système faute de place (dernière colonne de /proc/net/udp)."""
    wanted = f"{port:04X}"
    total = 0
    for text in tables:
        for line in text.splitlines()[1:]:
            fields = line.split()
            if len(fields) > 2 and fields[1].rsplit(":", 1)[-1].upper() == wanted:
                if fields[-1].isdigit():
                    total += int(fields[-1])
    return total


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


def screen_caps(display: tuple[int, int], dmabuf: bool) -> str:
    """Filtre imposant la taille exacte de l'écran (image plein écran).

    Constaté sur le Pi 3 : la TV annonce des dimensions physiques qui font croire à
    kmssink que ses pixels ne sont pas carrés (« pixel-aspect-ratio 54/59 ») ; pour
    garder les proportions, l'image sortait en 1920x988 avec des bandes noires. On impose
    donc la taille de l'écran (les pixels de la TV sont en réalité carrés).
    Guillemets : gst-launch lit la liste des formats (séparés par « ; ») en un seul bloc.
    """
    w, h = display
    plain = f"video/x-raw,width={w},height={h}"
    caps = f"video/x-raw(memory:DMABuf),width={w},height={h};{plain}" if dmabuf else plain
    # Apostrophes : retirées par shlex.split, elles gardent les guillemets pour gst-launch
    return f"""capsfilter caps='"{caps}"'"""


# Formes de pixel « standard » de kmssink (gst-plugins-bad, sys/kms/gstkmsutils.c,
# gst_video_calculate_device_ratio), dans le même ordre.
DEVICE_PAR_MAP = ((1, 1), (16, 15), (11, 10), (54, 59), (64, 45), (5, 3), (4, 3))


def device_par(display: tuple[int, int], size_mm: tuple[int, int]) -> tuple[int, int]:
    """Forme de pixel que kmssink attribue à l'écran (même calcul que GStreamer).

    kmssink (can-scale=false) n'accepte que des images ayant exactement cette forme de
    pixel. Elle vient de la taille physique annoncée par la TV : la TV de test annonce
    52x32 cm pour du 1920x1080, d'où 54/59 au lieu de 1/1.
    """
    width, height = display
    width_mm, height_mm = size_mm
    if not (width and height and width_mm and height_mm):
        ratio = 1.0
    else:
        ratio = (width_mm * height) / (height_mm * width)

    def delta(i: int, j: int) -> float:
        return abs(ratio - DEVICE_PAR_MAP[i][j] / DEVICE_PAR_MAP[i][1 - j])

    best, index, windex = delta(0, 0), 0, 0
    for i in range(1, len(DEVICE_PAR_MAP)):
        for j in (0, 1):
            current = delta(i, j)
            if current < best:
                best, index, windex = current, i, j
    return DEVICE_PAR_MAP[index][windex], DEVICE_PAR_MAP[index][windex ^ 1]


def edid_size_mm(edid: bytes) -> tuple[int, int]:
    """Taille physique annoncée par la TV (octets 21 et 22 de l'EDID, en cm), en mm.

    C'est la valeur que le noyau transmet à kmssink (drm_edid.c : width_cm * 10).
    """
    if len(edid) < 23:
        return 0, 0
    return edid[21] * 10, edid[22] * 10


def display_par(drm_dir: Path = DRM_DIR) -> tuple[int, int]:
    """Forme de pixel de l'écran HDMI branché selon kmssink (1/1 si inconnue)."""
    try:
        connectors = sorted(drm_dir.glob("card*-HDMI-A-*"))
    except OSError:
        return 1, 1
    for connector in connectors:
        try:
            if (connector / "status").read_text().strip() != "connected":
                continue
            edid = (connector / "edid").read_bytes()
            mode = parse_mode((connector / "modes").read_text())
        except OSError:
            continue
        if mode:
            return device_par(mode, edid_size_mm(edid))
    return 1, 1


def video_chain(decoder: str, hw_convert: bool = True,
                display: tuple[int, int] = DEFAULT_DISPLAY) -> str:
    """Décodage puis mise au format exact de l'écran (par la puce si possible)."""
    if hw_convert:
        convert = "v4l2convert"  # échelle sans garder de bandes : remplit l'écran
    else:
        convert = "videoconvert ! videoscale add-borders=false"
    return f"{decoder} ! {DROP_LATE_FRAMES} ! {convert} ! {screen_caps(display, hw_convert)}"


def build_command(decoder: str, alsa_device: str | None, port: int = wfd.RTP_PORT,
                  video_sink: str | None = None, hw_convert: bool = True,
                  display: tuple[int, int] = DEFAULT_DISPLAY) -> list[str]:
    """Arguments de gst-launch-1.0 (liste : pas de shell, pas d'injection possible)."""
    sink = video_sink or os.environ.get("BERRYCAST_VIDEO_SINK", VIDEO_SINK)
    audio_sink = "alsasink sync=false" + (f" device={alsa_device}" if alsa_device else "")
    description = (
        f"udpsrc port={port} buffer-size={UDP_BUFFER_BYTES} "
        "caps=\"application/x-rtp,media=video,clock-rate=90000,encoding-name=MP2T\" "
        "! rtpmp2tdepay "
        "! tsdemux name=demux "
        f"demux. ! queue max-size-time=0 max-size-buffers=0 ! h264parse "
        f"! {video_chain(decoder, hw_convert, display)} ! {sink} "
        "demux. ! queue max-size-time=0 max-size-buffers=0 ! aacparse ! avdec_aac "
        f"! audioconvert ! audioresample ! {AUDIO_OUT_CAPS} ! {audio_sink}"
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
                            hw_convert=has_hw_converter(), display=display_size())
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
