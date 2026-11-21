"""Miracast over Infrastructure (MS-MICE) : la vidéo passe par le Wi-Fi de la maison.

Pourquoi : NetworkManager (Raspberry Pi OS Trixie) supprime tout groupe Wi-Fi Direct qu'il
n'a pas créé lui-même (vérifié dans son code source, nm-supplicant-interface.c : sur le
signal GroupStarted, il crée un objet pour le groupe puis le jette, ce qui appelle
RemoveInterface sur wpa_supplicant). Le Miracast « classique » (groupe Wi-Fi Direct) est donc
impossible sans remplacer NetworkManager. MS-MICE n'a besoin d'aucun groupe :

1. Découverte : le Pi reste en écoute Wi-Fi Direct (comme à l'étape 02) et ajoute à ses
   réponses une « extension fabricant » Microsoft (WPS Vendor Extension, OUI 00:01:37) :
   capacité MICE + nom d'hôte + adresse IP. Il annonce aussi « _display._tcp » en mDNS.
2. Windows + K : le PC (sur le même réseau) se connecte au Pi en TCP sur le port 7250 et
   envoie SOURCE_READY (avec le port RTSP du PC).
3. Le Pi se connecte alors au RTSP du PC : même négociation M1–M7 que le Miracast classique
   (rtsp_sink.py), puis la vidéo arrive en RTP/UDP par le réseau de la maison.

Spécification : [MS-MICE] (Microsoft). Valeurs reprises de lazycast (newmice.py,
project.py ; Hsun-Wei Cho, GPL-3.0). Version sans chiffrement ni code PIN (comme lazycast) :
à n'utiliser que sur un réseau de confiance.
"""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

log = logging.getLogger("berrycast.miracast.mice")

MICE_PORT = 7250
MICROSOFT_OUI = bytes.fromhex("000137")

# Attributs de l'extension fabricant (découverte)
ATTR_CAPABILITY = 0x2001
ATTR_HOSTNAME = 0x2002
ATTR_IP_ADDRESS = 0x2005
CAPABILITY_VALUE = b"\x05"  # valeur de lazycast : MICE pris en charge

# Messages du protocole de projection (TCP 7250)
COMMANDS = {1: "SOURCE_READY", 2: "STOP_PROJECTION", 3: "SECURITY_HANDSHAKE",
            4: "SESSION_REQUEST", 5: "PIN_CHALLENGE", 6: "PIN_RESPONSE"}
TLV_TYPES = {0: "FRIENDLY_NAME", 2: "RTSP_PORT", 3: "SOURCE_ID", 4: "SECURITY_TOKEN",
             5: "SECURITY_OPTIONS", 6: "PIN_CHALLENGE", 7: "PIN_RESPONSE_REASON"}


def _attr(attr_type: int, value: bytes) -> bytes:
    return attr_type.to_bytes(2, "big") + len(value).to_bytes(2, "big") + value


def vendor_extension(hostname: str, ip: str | None) -> bytes:
    """Contenu de l'extension fabricant Microsoft annoncée en Wi-Fi Direct.

    Windows n'essaie que la première adresse IP : on n'en met qu'une.
    """
    data = MICROSOFT_OUI + _attr(ATTR_CAPABILITY, CAPABILITY_VALUE)
    data += _attr(ATTR_HOSTNAME, hostname.encode("utf-8"))
    if ip:
        data += _attr(ATTR_IP_ADDRESS, ip.encode("ascii"))
    return data


@dataclass
class MiceMessage:
    command: str
    version: int
    tlvs: dict[str, bytes] = field(default_factory=dict)

    @property
    def rtsp_port(self) -> int | None:
        raw = self.tlvs.get("RTSP_PORT")
        return int.from_bytes(raw, "big") if raw else None

    @property
    def friendly_name(self) -> str:
        raw = self.tlvs.get("FRIENDLY_NAME", b"")
        for encoding in ("utf-16-le", "utf-8"):  # Windows envoie de l'UTF-16 en général
            try:
                text = raw.decode(encoding).strip("\x00")
                if text.isprintable():
                    return text
            except UnicodeDecodeError:
                continue
        return ""


class MiceParser:
    """Découpe le flux TCP en messages : taille (2 o), version (1 o), commande (1 o), TLV
    (type 1 o, longueur 2 o, valeur). La taille inclut l'en-tête."""

    def __init__(self) -> None:
        self.buffer = b""

    def feed(self, data: bytes) -> list[MiceMessage]:
        self.buffer += data
        messages = []
        while len(self.buffer) >= 4:
            size = int.from_bytes(self.buffer[:2], "big")
            if size < 4:  # message incohérent : on jette le tampon
                self.buffer = b""
                break
            if len(self.buffer) < size:
                break
            raw, self.buffer = self.buffer[:size], self.buffer[size:]
            tlvs, pos = {}, 4
            while pos + 3 <= len(raw):
                tlv_type = raw[pos]
                length = int.from_bytes(raw[pos + 1:pos + 3], "big")
                tlvs[TLV_TYPES.get(tlv_type, f"TYPE_{tlv_type}")] = raw[pos + 3:pos + 3 + length]
                pos += 3 + length
            messages.append(MiceMessage(COMMANDS.get(raw[3], f"COMMAND_{raw[3]}"), raw[2], tlvs))
        return messages


def build_message(command: int, tlvs: list[tuple[int, bytes]] = (), version: int = 1) -> bytes:
    """Construit un message (utile pour les tests)."""
    body = b"".join(bytes([t]) + len(v).to_bytes(2, "big") + v for t, v in tlvs)
    return (4 + len(body)).to_bytes(2, "big") + bytes([version, command]) + body


class MiceServer:
    """Écoute le port 7250. on_ready(source_ip, rtsp_port, name) lance la projection ;
    on_stop() l'arrête (STOP_PROJECTION ou fermeture de la connexion)."""

    def __init__(self, on_ready: Callable[[str, int, str], None], on_stop: Callable[[], None],
                 port: int = MICE_PORT):
        self.on_ready = on_ready
        self.on_stop = on_stop
        self.sock = socket.create_server(("", port), family=socket.AF_INET6, dualstack_ipv6=True) \
            if socket.has_dualstack_ipv6() else socket.create_server(("", port))
        self.port = self.sock.getsockname()[1]
        self.stop_event = threading.Event()

    def serve_forever(self) -> None:
        self.sock.settimeout(1.0)
        while not self.stop_event.is_set():
            try:
                conn, addr = self.sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(target=self.handle, args=(conn, addr[0]), daemon=True).start()

    def handle(self, conn: socket.socket, peer: str) -> None:
        source_ip = peer.removeprefix("::ffff:")  # adresse IPv4 vue par une socket IPv6
        log.info("Connexion MICE de %s", source_ip)
        parser = MiceParser()
        started = False
        conn.settimeout(1.0)
        try:
            while not self.stop_event.is_set():
                try:
                    data = conn.recv(4096)
                except TimeoutError:
                    continue
                if not data:
                    break
                for msg in parser.feed(data):
                    log.info("MICE : %s %s", msg.command,
                             {k: v.hex() for k, v in msg.tlvs.items() if k != "SECURITY_TOKEN"})
                    if msg.command == "SOURCE_READY" and not started:
                        started = True
                        self.on_ready(source_ip, msg.rtsp_port or 7236, msg.friendly_name)
                    elif msg.command == "STOP_PROJECTION":
                        self.on_stop()
                        return
        except OSError as exc:
            log.info("Connexion MICE terminée : %s", exc)
        finally:
            conn.close()
            if started:
                self.on_stop()

    def close(self) -> None:
        self.stop_event.set()
        self.sock.close()


AVAHI_SERVICE_FILE = "/etc/avahi/services/berrycast-display.service"


def container_id(machine_id: str) -> str:
    """Identifiant stable de l'appareil (dérivé de /etc/machine-id), format UUID."""
    import hashlib
    import uuid

    digest = hashlib.sha256(("berrycast-mice:" + machine_id.strip()).encode()).digest()
    return str(uuid.UUID(bytes=digest[:16])).upper()


def avahi_service(container: str) -> str:
    """Fichier de service avahi : annonce mDNS « _display._tcp » (port 7250) cherchée par
    Windows pour Miracast over Infrastructure (comme « avahi-publish-service » de lazycast)."""
    return f"""<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<!-- BerryCast : Miracast over Infrastructure (MS-MICE). Fichier généré automatiquement. -->
<service-group>
  <name replace-wildcards="yes">%h</name>
  <service>
    <type>_display._tcp</type>
    <port>{MICE_PORT}</port>
    <txt-record>container_id={{{container}}}</txt-record>
  </service>
</service-group>
"""
