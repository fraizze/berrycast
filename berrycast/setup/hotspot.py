"""Wi-Fi temporaire « BerryCast-Setup-XXXX » (point d'accès) et scan des réseaux.

Contraintes de la puce du Pi 3 (une seule radio, BCM43430) :
- on SCANNE les réseaux AVANT de passer en point d'accès (ensuite la radio est occupée) ;
- PMF (protection des trames de gestion) DÉSACTIVÉ : sinon les iPhone refusent de se
  connecter au point d'accès du Pi 3 (problème déjà rencontré) ;
- WPA2 uniquement (RSN + CCMP), bande 2,4 GHz, économie d'énergie désactivée.

Le point d'accès est créé par NetworkManager en mode « partagé » (adresse 10.42.0.1,
serveur DHCP/DNS dnsmasq fourni par NetworkManager). Le fichier
/etc/NetworkManager/dnsmasq-shared.d/berrycast-captive.conf fait répondre 10.42.0.1 à
TOUS les noms de domaine : c'est ce qui ouvre la page toute seule (portail captif).
"""

from __future__ import annotations

import logging
import secrets
import subprocess
from pathlib import Path

from berrycast.dev.nm import split_terse

log = logging.getLogger(__name__)

CONNECTION_NAME = "berrycast-setup"
SSID_PREFIX = "BerryCast-Setup-"
WIFI_IFACE = "wlan0"
AP_ADDRESS = "10.42.0.1"
AP_CHANNEL = 6
# Mot de passe facile à lire et à taper : sans 0/O, 1/l/i
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
PASSWORD_LENGTH = 8


def setup_ssid(mac: str) -> str:
    """« BerryCast-Setup-XXXX » : XXXX = 4 derniers chiffres hexadécimaux de l'adresse MAC."""
    digits = mac.replace(":", "").replace("-", "").upper()
    return SSID_PREFIX + (digits[-4:] if len(digits) >= 4 else "0000")


def random_password(length: int = PASSWORD_LENGTH) -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def wifi_mac(iface: str = WIFI_IFACE) -> str:
    try:
        return Path(f"/sys/class/net/{iface}/address").read_text().strip()
    except OSError:
        return ""


def ap_connection_args(ssid: str, password: str, channel: int = AP_CHANNEL) -> list[str]:
    """Arguments « nmcli connection add » du point d'accès (fonction pure, testée)."""
    return [
        "nmcli", "connection", "add",
        "type", "wifi",
        "ifname", WIFI_IFACE,
        "con-name", CONNECTION_NAME,
        "ssid", ssid,
        "connection.autoconnect", "no",  # jamais au démarrage tout seul
        "802-11-wireless.mode", "ap",
        "802-11-wireless.band", "bg",
        "802-11-wireless.channel", str(channel),
        "802-11-wireless.powersave", "2",  # 2 = désactivé
        "ipv4.method", "shared",
        "ipv4.addresses", f"{AP_ADDRESS}/24",
        "ipv6.method", "disabled",
        "wifi-sec.key-mgmt", "wpa-psk",
        "wifi-sec.proto", "rsn",
        "wifi-sec.pairwise", "ccmp",
        "wifi-sec.group", "ccmp",
        "wifi-sec.pmf", "disable",  # indispensable pour les iPhone avec la puce du Pi 3
        "wifi-sec.psk", password,
    ]


def _nmcli(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["nmcli", *args], capture_output=True, text=True, timeout=60, check=check
    )


def parse_scan(output: str) -> list[dict]:
    """Lit « nmcli -t -f SSID,SIGNAL,SECURITY,CHAN device wifi list ».

    Garde un seul exemplaire par nom (le meilleur signal), ignore les réseaux cachés et
    nos propres points d'accès BerryCast-Setup, trie du plus fort au plus faible.
    """
    best: dict[str, dict] = {}
    for line in output.splitlines():
        fields = split_terse(line)
        if len(fields) < 4:
            continue
        ssid, signal, security, chan = fields[:4]
        if not ssid or ssid.startswith(SSID_PREFIX):
            continue
        network = {
            "ssid": ssid,
            "signal": int(signal) if signal.isdigit() else 0,
            "secure": bool(security.strip()) and security.strip() != "--",
            "security": security.strip(),
            "channel": int(chan) if chan.isdigit() else None,
        }
        if ssid not in best or network["signal"] > best[ssid]["signal"]:
            best[ssid] = network
    return sorted(best.values(), key=lambda n: (-n["signal"], n["ssid"].casefold()))


def scan_networks() -> list[dict]:
    """Scan des réseaux Wi-Fi autour (à faire AVANT de démarrer le point d'accès)."""
    result = _nmcli("-t", "-f", "SSID,SIGNAL,SECURITY,CHAN", "device", "wifi", "list",
                    "--rescan", "yes")
    return parse_scan(result.stdout)


def active_wifi_connection() -> str | None:
    """Nom de la connexion Wi-Fi active sur wlan0 (pour la rétablir ensuite)."""
    for line in _nmcli("-t", "-f", "DEVICE,CONNECTION", "device").stdout.splitlines():
        fields = split_terse(line)
        if len(fields) >= 2 and fields[0] == WIFI_IFACE and fields[1]:
            return fields[1] if fields[1] != CONNECTION_NAME else None
    return None


def start_ap(ssid: str, password: str) -> None:
    _nmcli("connection", "delete", CONNECTION_NAME)
    _nmcli(*ap_connection_args(ssid, password)[1:], check=True)
    _nmcli("connection", "up", CONNECTION_NAME, check=True)
    log.info("Point d'accès %s démarré", ssid)


def stop_ap(restore: str | None = None) -> None:
    _nmcli("connection", "down", CONNECTION_NAME)
    _nmcli("connection", "delete", CONNECTION_NAME)
    log.info("Point d'accès arrêté")
    if restore:
        result = _nmcli("connection", "up", restore)
        log.info("Retour sur « %s » : %s", restore, "OK" if result.returncode == 0 else "échec")
