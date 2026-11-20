"""Liste des réseaux Wi-Fi autour du Pi et détection du pays (pour le premier lancement).

Le Pi reste un simple client Wi-Fi pendant la configuration : il peut scanner à tout
moment (pas de point d'accès, donc pas de conflit sur l'unique radio du Pi 3).
"""

from __future__ import annotations

import subprocess
from collections import Counter

from berrycast.countries import normalize_country
from berrycast.dev.nm import split_terse


def parse_scan(output: str) -> list[dict]:
    """Lit « nmcli -t -f SSID,SIGNAL,SECURITY device wifi list ».

    Un seul exemplaire par nom (le meilleur signal), sans les réseaux cachés,
    trié du plus fort au plus faible.
    """
    best: dict[str, dict] = {}
    for line in output.splitlines():
        fields = split_terse(line)
        if len(fields) < 3:
            continue
        ssid, signal, security = fields[:3]
        if not ssid:
            continue
        security = security.strip()
        network = {
            "ssid": ssid,
            "signal": int(signal) if signal.isdigit() else 0,
            "secure": bool(security) and security != "--",
        }
        if ssid not in best or network["signal"] > best[ssid]["signal"]:
            best[ssid] = network
    return sorted(best.values(), key=lambda n: (-n["signal"], n["ssid"].casefold()))


def scan(rescan: bool = False) -> list[dict]:
    """Réseaux visibles. rescan=True relance une recherche (quelques secondes)."""
    cmd = ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list",
           "--rescan", "yes" if rescan else "auto"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_scan(out)


def parse_scan_countries(iw_output: str) -> str | None:
    """Pays le plus annoncé par les box Wi-Fi autour (élément « Country » des balises)."""
    counts: Counter[str] = Counter()
    for line in iw_output.splitlines():
        line = line.strip()
        if line.startswith("Country:"):
            code = normalize_country(line.split()[1] if len(line.split()) > 1 else "")
            if code:
                counts[code] += 1
    return counts.most_common(1)[0][0] if counts else None


def detect_country() -> str | None:
    """Pays deviné grâce aux box Wi-Fi voisines (None si rien de fiable)."""
    try:
        out = subprocess.run(["iw", "dev", "wlan0", "scan", "dump"],
                             capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_scan_countries(out)
