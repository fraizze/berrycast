"""Briques Wi-Fi Display (Miracast) sans réseau ni D-Bus : testables sur PC.

- éléments WFD publiés en Wi-Fi Direct (WFDIEs) ;
- code PIN WPS à 8 chiffres ;
- messages RTSP : lecture (avec Content-Length) et écriture ;
- réponses du récepteur (« sink ») aux GET_PARAMETER de la source (M3).

Valeurs reprises de lazycast (Hsun-Wei Cho, GPL-3.0), testé avec Windows 10/11 :
https://github.com/homeworkc/lazycast
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

RTSP_PORT = 7236  # port RTSP de la source (Windows)
RTP_PORT = 1028  # port UDP où le Pi reçoit la vidéo

# --- Éléments Wi-Fi Display (sous-éléments : id, longueur sur 2 octets, données) ------
# 0 « Device Information » : 0x0011 = récepteur principal + session disponible,
#   port RTSP 7236 (0x1c44), débit max 300 Mb/s (0x012c)
# 1 « Associated BSSID » : vide ; 6 « Coupled Sink » : non couplé
WFD_IES = bytes.fromhex("000006" "0011" "1c44" "012c"
                        "010006" "000000000000"
                        "060007" "00000000000000")

# Type d'appareil WPS : catégorie 7 (écran), OUI Wi-Fi Alliance, sous-catégorie 1 (TV)
PRIMARY_DEVICE_TYPE_TV = bytes.fromhex("0007" "0050f204" "0001")

# --- Capacités annoncées (réponse à M3) ---------------------------------------------
# AAC 2 canaux 48 kHz (décodé par GStreamer).
# Vidéo H.264 « Constrained High », niveau 4.1 (0x08), modes CEA 640x480p60 (bit 0,
# obligatoire), 1280x720p30 (bit 5) et 1920x1080p30 (bit 7) = 0x000000A1, aucun mode VESA
# ni HH. Constaté sur le Pi : avec les valeurs de lazycast (tous les modes, niveau 4.2),
# Windows choisissait 1024x768 à 60 i/s niveau 4.2, refusé par le décodeur du Pi 3.
AUDIO_CODECS = "AAC 00000001 00"
VIDEO_FORMATS = "00 00 02 08 000000A1 00000000 00000000 00 0000 0000 00 none none"


def wps_checksum(pin7: int) -> int:
    """Chiffre de contrôle d'un PIN WPS (8e chiffre), algorithme de la norme WPS."""
    accum, n = 0, pin7
    weights = (3, 1, 3, 1, 3, 1, 3)
    digits = [int(d) for d in f"{n:07d}"]
    for digit, weight in zip(digits, weights, strict=True):
        accum += digit * weight
    return (10 - accum % 10) % 10


def new_pin() -> str:
    """PIN WPS aléatoire à 8 chiffres, avec chiffre de contrôle valide."""
    base = secrets.randbelow(10_000_000)
    return f"{base:07d}{wps_checksum(base)}"


def format_pin(pin: str) -> str:
    """« 12345670 » -> « 1234 5670 » (comme Windows l'affiche)."""
    return f"{pin[:4]} {pin[4:]}" if len(pin) == 8 else pin


# --- Messages RTSP -----------------------------------------------------------------


@dataclass
class RtspMessage:
    first_line: str
    headers: dict[str, str] = field(default_factory=dict)  # noms en minuscules
    body: str = ""

    @property
    def is_response(self) -> bool:
        return self.first_line.startswith("RTSP/")

    @property
    def method(self) -> str:
        return "" if self.is_response else self.first_line.split(" ", 1)[0]

    @property
    def status(self) -> int:
        parts = self.first_line.split()
        return int(parts[1]) if self.is_response and len(parts) > 1 else 0

    @property
    def cseq(self) -> str:
        return self.headers.get("cseq", "")

    def parameters(self) -> list[str]:
        """Noms des paramètres demandés (GET_PARAMETER) : une ligne = un nom."""
        return [line.strip() for line in self.body.splitlines() if line.strip()]

    def values(self) -> dict[str, str]:
        """« nom: valeur » du corps (SET_PARAMETER, réponses)."""
        out = {}
        for line in self.body.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                out[key.strip()] = value.strip()
        return out


class RtspParser:
    """Découpe le flux TCP en messages RTSP complets (en-têtes + corps de Content-Length)."""

    def __init__(self) -> None:
        self.buffer = b""

    def feed(self, data: bytes) -> list[RtspMessage]:
        self.buffer += data
        messages = []
        while True:
            end = self.buffer.find(b"\r\n\r\n")
            if end < 0:
                break
            head = self.buffer[:end].decode("utf-8", errors="replace")
            lines = head.split("\r\n")
            # Ignore d'éventuelles lignes vides avant le message
            while lines and not lines[0].strip():
                lines.pop(0)
            if not lines:
                self.buffer = self.buffer[end + 4:]
                continue
            headers = {}
            for line in lines[1:]:
                if ":" in line:
                    key, _, value = line.partition(":")
                    headers[key.strip().lower()] = value.strip()
            length = int(headers.get("content-length", "0") or 0)
            total = end + 4 + length
            if len(self.buffer) < total:
                break  # corps pas encore arrivé
            body = self.buffer[end + 4:total].decode("utf-8", errors="replace")
            self.buffer = self.buffer[total:]
            messages.append(RtspMessage(lines[0].strip(), headers, body))
        return messages


def build(first_line: str, headers: dict[str, str] | None = None, body: str = "") -> bytes:
    lines = [first_line]
    for key, value in (headers or {}).items():
        lines.append(f"{key}: {value}")
    if body:
        lines.append("Content-Type: text/parameters")
        lines.append(f"Content-Length: {len(body.encode())}")
    return ("\r\n".join(lines) + "\r\n\r\n" + body).encode()


def response(cseq: str, extra: dict[str, str] | None = None, body: str = "") -> bytes:
    headers = {"CSeq": cseq}
    headers.update(extra or {})
    return build("RTSP/1.0 200 OK", headers, body)


def sink_parameters(device_name: str) -> dict[str, str]:
    """Valeurs du récepteur pour chaque paramètre que la source peut demander (M3)."""
    return {
        "wfd_client_rtp_ports": f"RTP/AVP/UDP;unicast {RTP_PORT} 0 mode=play",
        "wfd_audio_codecs": AUDIO_CODECS,
        "wfd_video_formats": VIDEO_FORMATS,
        "wfd_3d_video_formats": "none",
        "wfd_coupled_sink": "none",
        "wfd_connector_type": "05",  # HDMI
        "wfd_uibc_capability": "none",
        "wfd_standby_resume_capability": "none",
        "wfd_content_protection": "none",  # pas de HDCP (limite connue)
        "wfd_idr_request_capability": "1",
        "intel_friendly_name": device_name,
        "intel_sink_manufacturer_name": "BerryCast",
        "intel_sink_model_name": "BerryCast",
        "intel_sink_version": "0.1",
        "intel_sink_device_URL": "none",
        "microsoft_latency_management_capability": "none",
        "microsoft_format_change_capability": "none",
        "microsoft_diagnostics_capability": "none",
        "microsoft_cpu_capability": "none",
        "microsoft_teardown_on_disconnect_capability": "none",
    }


def answer_get_parameter(requested: list[str], device_name: str) -> str:
    """Corps de la réponse à M3 : seulement les paramètres demandés que l'on connaît.

    Un paramètre inconnu (wfd_display_edid…) est simplement omis : la source utilise
    alors sa valeur par défaut.
    """
    known = sink_parameters(device_name)
    lines = [f"{name}: {known[name]}" for name in requested if name in known]
    return "".join(line + "\r\n" for line in lines)


def server_port(transport: str) -> str | None:
    """« RTP/AVP/UDP;unicast;client_port=1028;server_port=5000 » -> « 5000 »."""
    for part in transport.split(";"):
        if part.strip().startswith("server_port="):
            return part.split("=", 1)[1].split("-")[0].strip()
    return None


def session_id(session_header: str) -> str:
    """« 6B8B4567;timeout=30 » -> « 6B8B4567 »."""
    return session_header.split(";", 1)[0].strip()
