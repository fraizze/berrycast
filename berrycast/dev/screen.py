"""Écran HDMI de l'image de développement : « BerryCast dev », adresse IP, état du Wi-Fi.

Fond noir, texte blanc, centré, écrit directement sur la console tty1 (pas de
serveur graphique). Version minimale en attendant le vrai écran (étape 05).

Lancé par berrycast-devscreen.service sous l'utilisateur « berrycast », sans root :
systemd ouvre lui-même /dev/tty1 et le donne au programme comme SORTIE STANDARD
(StandardOutput=tty). Le programme écrit donc simplement sur sa sortie standard.

Pour un essai à la main, la variable BERRYCAST_TTY permet d'écrire ailleurs
(sinon, lancé dans une session SSH, l'écran s'affiche dans le terminal SSH).
"""

from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from berrycast.countries import WORLD_REGDOMAIN, parse_iw_reg_get
from berrycast.dev.nm import split_terse

TTY = os.environ.get("BERRYCAST_TTY")  # None = sortie standard (cas normal)
STATE_FILE = Path(os.environ.get("BERRYCAST_STATE_DIR", "/var/lib/berrycast")) / "devsetup.json"
BUILD_INFO = Path(os.environ.get("BERRYCAST_HOME", "/opt/berrycast")) / "BUILD_INFO"
REFRESH_SECONDS = 3
FULL_REDRAW_SECONDS = 30  # redessine de toute façon (efface d'éventuels messages du noyau)

# Séquences de contrôle de la console Linux
CLEAR = "\033[0m\033[2J\033[H"
HIDE_CURSOR = "\033[?25l"
NO_BLANKING = "\033[9;0]"  # ne jamais éteindre l'écran
BOLD, NORMAL = "\033[1m", "\033[0m"


@dataclass
class Info:
    hostname: str = "berrycast"
    wifi_state: str = "unknown"  # état NetworkManager de wlan0
    ssid: str | None = None
    signal: int | None = None
    addresses: dict[str, str] = field(default_factory=dict)  # interface -> adresse IPv4
    ssh_password_set: bool | None = None
    regdomain: str | None = None  # pays Wi-Fi appliqué (« FR », « 00 » = international)
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    build: str = ""


def nmcli(*args: str) -> str:
    try:
        return subprocess.run(
            ["nmcli", *args], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def gather() -> Info:
    """Collecte l'état actuel (sans droits particuliers)."""
    info = Info(hostname=socket.gethostname())

    for line in nmcli("-t", "-f", "DEVICE,TYPE,STATE", "device").splitlines():
        dev, typ, state = (split_terse(line) + ["", "", ""])[:3]
        if typ == "wifi" and dev == "wlan0":
            info.wifi_state = state
        if typ in ("wifi", "ethernet") and state == "connected":
            out = nmcli("-g", "IP4.ADDRESS", "device", "show", dev).strip()
            if out:
                # « 172.20.10.2/28 » (plusieurs adresses séparées par « | »)
                info.addresses[dev] = out.split("|")[0].strip().split("/")[0]

    for line in nmcli("-t", "-f", "ACTIVE,SSID,SIGNAL", "device", "wifi", "list",
                      "--rescan", "no").splitlines():
        active, ssid, signal = (split_terse(line) + ["", "", ""])[:3]
        if active == "yes":
            info.ssid = ssid
            info.signal = int(signal) if signal.isdigit() else None

    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        info.ssh_password_set = state.get("ssh_password_set")
        info.regdomain = live_regdomain() or state.get("regdomain")
        info.messages = state.get("messages", [])
        info.errors = state.get("errors", [])
    except (OSError, ValueError):
        pass

    try:
        build = dict(
            line.split("=", 1) for line in BUILD_INFO.read_text().splitlines() if "=" in line
        )
        info.build = f"{build.get('commit', '?')} du {build.get('date', '?')}"
    except OSError:
        pass

    return info


def live_regdomain() -> str | None:
    """Pays Wi-Fi appliqué EN CE MOMENT (il peut changer après le démarrage : réglage
    enregistré, ou pays annoncé par la box Wi-Fi). Lecture sans droits particuliers."""
    try:
        out = subprocess.run(["/usr/sbin/iw", "reg", "get"], capture_output=True, text=True,
                             timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_iw_reg_get(out)


WIFI_STATES = {
    "connected": "connecté",
    "connecting": "connexion en cours…",
    "disconnected": "non connecté",
    "unavailable": "indisponible (pays non réglé ?)",
    "unmanaged": "non géré",
}


def render_lines(info: Info) -> list[str]:
    """Texte à afficher (fonction pure, testée sans Raspberry Pi)."""
    lines = ["BerryCast dev", ""]

    if info.wifi_state == "connected" and info.ssid:
        signal = f" ({info.signal} %)" if info.signal is not None else ""
        lines.append(f"Wi-Fi : connecté à « {info.ssid} »{signal}")
    else:
        lines.append(f"Wi-Fi : {WIFI_STATES.get(info.wifi_state, info.wifi_state)}")
        if info.wifi_state != "connected":
            lines.append("(branchez un clavier : la configuration s'ouvre toute seule)")

    lines.append("")
    if info.addresses:
        for dev, ip in info.addresses.items():
            label = "Wi-Fi" if dev.startswith("wlan") else "Câble"
            lines.append(f"Adresse IP ({label}) : {ip}")
        first_ip = next(iter(info.addresses.values()))
        lines += ["", f"SSH : ssh pi@{info.hostname}.local", f"  ou  ssh pi@{first_ip}"]
    else:
        lines.append("Adresse IP : aucune")

    warnings = []
    if info.regdomain == WORLD_REGDOMAIN:
        warnings.append("ATTENTION : pays Wi-Fi non défini, réglage international utilisé")
        warnings.append("(champ « Pays » de la configuration, ou berrycast-wifi.txt)")
    elif info.regdomain:
        lines.append(f"Pays Wi-Fi : {info.regdomain}")
    if info.ssh_password_set is False:
        warnings.append("ATTENTION : mot de passe SSH non défini (configuration au clavier)")
    if warnings:
        lines += [""] + warnings

    if info.errors:
        lines.append("")
        lines += [f"ERREUR : {e}" for e in info.errors]

    if info.build:
        lines += ["", f"version {info.build}"]
    return lines


def terminal_size(fd: int) -> tuple[int, int]:
    """(colonnes, lignes) de la console ; 80x25 si inconnu."""
    # Importés ici : ces modules n'existent que sous Linux (les tests tournent aussi sous Windows).
    import fcntl
    import termios

    try:
        rows, cols, _, _ = struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))
        if rows and cols:
            return cols, rows
    except OSError:
        pass
    return 80, 25


def layout(lines: list[str], cols: int, rows: int) -> str:
    """Centre le texte horizontalement et verticalement ; titre en gras."""
    lines = [line[:cols] for line in lines[:rows]]
    top = max(0, (rows - len(lines)) // 2)
    out = [CLEAR, HIDE_CURSOR, NO_BLANKING, "\n" * top]
    for i, line in enumerate(lines):
        pad = " " * max(0, (cols - len(line)) // 2)
        text = f"{BOLD}{line}{NORMAL}" if i == 0 else line
        out.append(pad + text + ("\n" if i < len(lines) - 1 else ""))
    return "".join(out)


def open_output() -> int:
    """Descripteur où écrire : la sortie standard (tty1 donné par systemd), ou BERRYCAST_TTY."""
    if TTY:
        return os.open(TTY, os.O_WRONLY | os.O_NOCTTY)
    return sys.stdout.fileno()


def write_all(fd: int, data: bytes) -> None:
    """Écrit tout (os.write peut n'écrire qu'une partie sur un terminal)."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def main() -> int:
    target = TTY or "la sortie standard"
    if not TTY and not os.isatty(sys.stdout.fileno()):
        print(
            "Écran : la sortie standard n'est pas un terminal "
            "(vérifier StandardOutput=tty et TTYPath= dans le service).",
            file=sys.stderr,
        )
    fd = open_output()
    last_text, last_full, failures = None, 0.0, 0
    while True:
        try:
            cols, rows = terminal_size(fd)
            lines = render_lines(gather())
            now = time.monotonic()
            if lines != last_text or now - last_full > FULL_REDRAW_SECONDS:
                write_all(fd, layout(lines, cols, rows).encode("utf-8"))
                last_text, last_full = lines, now
            failures = 0
        except OSError as exc:
            failures += 1
            print(f"Écran : erreur d'écriture sur {target} : {exc}", file=sys.stderr)
            if failures >= 3:
                # On quitte : systemd relance le service et rouvre proprement tty1.
                return 1
        time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
