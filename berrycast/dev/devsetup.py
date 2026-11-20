"""Applique berrycast-wifi.txt au démarrage (image de développement uniquement).

Lancé par berrycast-devsetup.service, en root : c'est nécessaire pour changer le
mot de passe de l'utilisateur « pi », le pays Wi-Fi et les connexions réseau du
système. Le service s'arrête dès que c'est fait (Type=oneshot).

Étapes :
1. lire /boot/firmware/berrycast-wifi.txt ;
2. appliquer le pays Wi-Fi, le mot de passe SSH, puis le Wi-Fi (NetworkManager) ;
3. réécrire le fichier SANS les mots de passe, avec un compte rendu en haut ;
4. enregistrer l'état dans /var/lib/berrycast/devsetup.json pour l'écran HDMI.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from berrycast.dev import wifi_file
from berrycast.dev.nm import split_terse

log = logging.getLogger("berrycast.devsetup")

BOOT_DIR = Path(os.environ.get("BERRYCAST_BOOT_DIR", "/boot/firmware"))
STATE_FILE = Path(os.environ.get("BERRYCAST_STATE_DIR", "/var/lib/berrycast")) / "devsetup.json"
DEV_USER = "pi"
CONNECTION_NAME = "berrycast-wifi"
WIFI_IFACE = "wlan0"


def run(
    cmd: list[str], stdin: str | None = None, check: bool = True
) -> subprocess.CompletedProcess:
    """Lance une commande système (jamais via un shell : pas d'injection possible)."""
    log.info("Commande : %s", cmd[0] + " " + " ".join(cmd[1:3]))  # pas d'arguments secrets
    return subprocess.run(
        cmd, input=stdin, capture_output=True, text=True, timeout=90, check=check
    )


def apply_country(country: str) -> None:
    run(["raspi-config", "nonint", "do_wifi_country", country])


def enable_wifi_radio() -> None:
    """Débloque la radio Wi-Fi (bloquée par défaut tant que le pays n'est pas réglé)."""
    run(["rfkill", "unblock", "wifi"], check=False)
    run(["nmcli", "radio", "wifi", "on"], check=False)


def wait_for_wifi_device(timeout: float = 20) -> bool:
    """Attend que NetworkManager voie l'interface Wi-Fi comme utilisable."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        out = run(["nmcli", "-t", "-f", "DEVICE,STATE", "device"], check=False).stdout
        for line in out.splitlines():
            fields = split_terse(line)
            if len(fields) >= 2 and fields[0] == WIFI_IFACE and fields[1] != "unavailable":
                return True
        time.sleep(1)
    return False


def visible_ssids() -> list[str]:
    out = run(
        ["nmcli", "-t", "-f", "SSID", "device", "wifi", "list", "--rescan", "yes"], check=False
    ).stdout
    return [split_terse(line)[0] for line in out.splitlines() if line.strip()]


def configured_ssid() -> str | None:
    """Nom du Wi-Fi déjà enregistré dans la connexion « berrycast-wifi » (None si absente)."""
    result = run(
        ["nmcli", "-g", "802-11-wireless.ssid", "connection", "show", CONNECTION_NAME],
        check=False,
    )
    if result.returncode != 0:
        return None
    return split_terse(result.stdout.rstrip("\n"))[0] or None


def apply_ssh_password(password: str) -> None:
    # Le mot de passe passe par l'entrée standard, pas par la ligne de commande.
    run(["chpasswd"], stdin=f"{DEV_USER}:{password}\n")


def ssh_password_is_set() -> bool:
    """« passwd -S pi » renvoie « pi P ... » si un mot de passe utilisable existe."""
    out = run(["passwd", "-S", DEV_USER], check=False).stdout.split()
    return len(out) >= 2 and out[1] == "P"


def apply_wifi(ssid: str, psk: str | None) -> str:
    """Crée (ou remplace) la connexion Wi-Fi « berrycast-wifi » et tente de s'y connecter.

    Remarque : nmcli reçoit le mot de passe Wi-Fi en argument. C'est visible très
    brièvement dans la liste des processus du Pi (par root, au démarrage) :
    acceptable pour une image de développement.
    """
    run(["nmcli", "connection", "delete", CONNECTION_NAME], check=False)
    cmd = [
        "nmcli", "connection", "add",
        "type", "wifi",
        "ifname", WIFI_IFACE,
        "con-name", CONNECTION_NAME,
        "ssid", ssid,
        "connection.autoconnect", "yes",
        # 0 = réessayer indéfiniment (utile si le partage de connexion est éteint)
        "connection.autoconnect-retries", "0",
    ]
    if psk:
        cmd += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", psk]
    run(cmd)
    result = run(["nmcli", "--wait", "30", "connection", "up", CONNECTION_NAME], check=False)
    if result.returncode == 0:
        return f"Wi-Fi « {ssid} » : connecté"
    return f"Wi-Fi « {ssid} » : enregistré, pas encore joignable (nouvel essai automatique)"


def write_boot_file(path: Path, content: str) -> None:
    """Remplace le fichier d'un coup (fichier temporaire + renommage), puis force l'écriture."""
    fd, tmp = tempfile.mkstemp(prefix=".berrycast-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    if hasattr(os, "sync"):  # Linux : vide les caches vers la carte SD
        os.sync()


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o644)  # lisible par l'écran (aucun secret dedans)
    os.replace(tmp, STATE_FILE)


def apply_file(path: Path) -> tuple[list[str], list[str]]:
    """Applique le fichier. Renvoie (messages, erreurs)."""
    values = wifi_file.parse(path.read_text(encoding="utf-8", errors="replace"))
    settings = wifi_file.validate(values)
    messages: list[str] = []
    errors = list(settings.errors)

    # On n'agit que s'il y a du nouveau : un mot de passe à appliquer, une erreur à
    # signaler, ou un nom de Wi-Fi différent de celui déjà enregistré (réseau ouvert).
    # Sinon (cas normal après le premier démarrage), on ne touche à rien.
    new_ssid = settings.ssid and settings.ssid != configured_ssid()
    if not (settings.has_secrets() or errors or new_ssid):
        return [], []

    if settings.country:
        try:
            apply_country(settings.country)
            messages.append(f"Pays Wi-Fi : {settings.country}")
        except subprocess.CalledProcessError:
            errors.append(f"pays « {settings.country} » refusé par le système")

    if settings.ssh_password:
        try:
            apply_ssh_password(settings.ssh_password)
            messages.append(f"Mot de passe SSH de « {DEV_USER} » : enregistré")
        except subprocess.CalledProcessError:
            errors.append("impossible d'enregistrer le mot de passe SSH")

    if settings.ssid:
        enable_wifi_radio()
        wait_for_wifi_device()
        ssid = wifi_file.pick_ssid(settings.ssid, visible_ssids())
        if ssid != settings.ssid:
            messages.append(f"Nom du Wi-Fi corrigé : « {ssid} »")
        try:
            messages.append(apply_wifi(ssid, settings.psk))
        except subprocess.CalledProcessError as exc:
            errors.append(f"Wi-Fi non enregistré : {exc.stderr.strip() or exc}")

    # Réécriture du fichier, sans mot de passe, avec le compte rendu en haut.
    stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
    report = [f"Lu par le Raspberry Pi le {stamp}"]
    report += messages + [f"ERREUR : {e}" for e in errors]
    write_boot_file(
        path,
        wifi_file.render(
            ssid=values.get(wifi_file.KEY_SSID, ""),
            country=values.get(wifi_file.KEY_COUNTRY, ""),
            messages=report,
        ),
    )
    return messages, errors


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    path = BOOT_DIR / wifi_file.FILE_NAME
    state = load_state()

    if not path.exists():
        # Fichier supprimé : on remet un modèle vide pour pouvoir le remplir plus tard.
        write_boot_file(path, wifi_file.render(country="FR"))
        log.info("Modèle %s recréé.", path)
    else:
        try:
            messages, errors = apply_file(path)
        except Exception as exc:  # ne jamais bloquer le démarrage
            log.exception("Erreur pendant l'application de %s", path)
            messages, errors = [], [f"erreur inattendue : {exc}"]
        if messages or errors:
            state["last_applied"] = datetime.now().isoformat(timespec="seconds")
            state["messages"] = messages
            state["errors"] = errors
        for m in messages:
            log.info("%s", m)
        for e in errors:
            log.warning("%s", e)

    state["ssh_password_set"] = ssh_password_is_set()
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
