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

from berrycast import countries
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


CMDLINE = BOOT_DIR / "cmdline.txt"
REGDOM_PARAM = "cfg80211.ieee80211_regdom="


PROC_CMDLINE = Path("/proc/cmdline")
# Réglages ajoutés par le micrologiciel du Pi devant cmdline.txt (visibles dans /proc/cmdline)
FIRMWARE_PREFIXES = ("coherent_pool=", "8250.nr_uarts=", "snd_bcm2835.", "vc_mem.",
                     "cgroup_disable=", "bcm2708_fb.", "smsc95xx.", "video=", "dwc_otg.")


class CmdlineError(ValueError):
    """cmdline.txt illisible ou contenu refusé (on ne l'écrit jamais dans ce cas)."""


def read_cmdline() -> list[str]:
    """Mots de cmdline.txt. Lève CmdlineError s'il est vide ou sans « root= » (abîmé)."""
    try:
        words = CMDLINE.read_text(encoding="utf-8").split()
    except OSError as exc:
        raise CmdlineError(f"cmdline.txt illisible : {exc}") from exc
    if not any(w.startswith("root=") for w in words):
        raise CmdlineError("cmdline.txt vide ou abîmé (pas de « root= »)")
    return words


def write_cmdline(words: list[str]) -> None:
    """Écrit cmdline.txt de façon sûre : jamais vide, toujours avec « root= », écriture
    atomique et forcée sur la carte (une coupure de courant ne doit pas l'abîmer)."""
    if not any(w.startswith("root=") for w in words):
        raise CmdlineError("refus d'écrire un cmdline.txt sans « root= »")
    write_boot_file(CMDLINE, " ".join(words) + "\n")
    if read_cmdline() != words:  # relecture de contrôle
        raise CmdlineError("cmdline.txt : la relecture ne correspond pas")


def with_regdomain(words: list[str], country: str | None) -> list[str]:
    """Mots de cmdline.txt avec le pays Wi-Fi demandé (None = aucun = international)."""
    kept = [w for w in words if not w.startswith(REGDOM_PARAM)]
    return kept + ([REGDOM_PARAM + country] if country else [])


def rebuild_from_proc(proc_cmdline: str) -> list[str]:
    """Reconstitue cmdline.txt à partir de /proc/cmdline (réglages du démarrage en cours).

    Le micrologiciel ajoute ses propres réglages devant ceux de cmdline.txt et remplace
    « serial0 » par le vrai nom du port série : on retire les premiers, on remet le second.
    """
    words = [w for w in proc_cmdline.split() if not w.startswith(FIRMWARE_PREFIXES)]
    fixed = []
    for w in words:
        for port in ("ttyS0", "ttyAMA0"):
            if w.startswith(f"console={port},"):
                w = "console=serial0," + w.split(",", 1)[1]
        fixed.append(w)
    return fixed


def repair_cmdline() -> str | None:
    """Au démarrage : si cmdline.txt est vide ou abîmé, le reconstruire. Renvoie un message."""
    try:
        read_cmdline()
        return None
    except CmdlineError as problem:
        try:
            words = rebuild_from_proc(PROC_CMDLINE.read_text(encoding="utf-8"))
            write_cmdline(words)
        except (OSError, CmdlineError) as exc:
            log.error("cmdline.txt abîmé et non réparé : %s (%s)", problem, exc)
            return f"cmdline.txt abîmé, réparation impossible : {exc}"
        log.warning("cmdline.txt réparé (%s)", problem)
        return "cmdline.txt était abîmé : réparé automatiquement"


def apply_country(country: str) -> None:
    """Règle le pays Wi-Fi : enregistré dans cmdline.txt (pour les prochains démarrages)
    et appliqué tout de suite. Même effet que « raspi-config nonint do_wifi_country »,
    mais avec une écriture sûre (constaté sur le Pi : cmdline.txt vidé après une coupure)."""
    code = countries.normalize_country(country)
    if code is None:
        raise CmdlineError(f"pays invalide : {country!r}")
    write_cmdline(with_regdomain(read_cmdline(), code))
    run(["iw", "reg", "set", code], check=False)


def apply_world_regdomain() -> None:
    """Réglage Wi-Fi international « 00 » : retire le pays de cmdline.txt et l'applique."""
    try:
        words = read_cmdline()
        new_words = with_regdomain(words, None)
        if new_words != words:
            write_cmdline(new_words)
    except (OSError, CmdlineError) as exc:
        log.warning("cmdline.txt non modifié : %s", exc)
    run(["iw", "reg", "set", countries.WORLD_REGDOMAIN], check=False)


def current_regdomain() -> str | None:
    """Pays Wi-Fi actuellement appliqué par le système (« FR », « 00 »…), None si inconnu."""
    return countries.parse_iw_reg_get(run(["iw", "reg", "get"], check=False).stdout)


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
    """Comme connect_wifi, mais renvoie seulement un message (berrycast-wifi.txt)."""
    ok, _ = connect_wifi(ssid, psk)
    if ok:
        return f"Wi-Fi « {ssid} » : connecté"
    return f"Wi-Fi « {ssid} » : enregistré, pas encore joignable (nouvel essai automatique)"


def connect_wifi(ssid: str, psk: str | None, wait: int = 30) -> tuple[bool, str]:
    """Crée (ou remplace) la connexion Wi-Fi « berrycast-wifi » et tente de s'y connecter.

    Renvoie (connecté ?, message d'erreur de NetworkManager).
    Remarque : nmcli reçoit le mot de passe Wi-Fi en argument. C'est visible très
    brièvement dans la liste des processus du Pi (par root) : acceptable pour une
    image de développement.
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
    result = run(["nmcli", "--wait", str(wait), "connection", "up", CONNECTION_NAME],
                 check=False)
    return result.returncode == 0, (result.stderr or result.stdout).strip()


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


def apply_file(path: Path) -> tuple[list[str], list[str], list[str]]:
    """Applique le fichier. Renvoie (messages, avertissements, erreurs)."""
    values = wifi_file.parse(path.read_text(encoding="utf-8", errors="replace"))
    settings = wifi_file.validate(values)
    messages: list[str] = []
    warnings = list(settings.warnings)
    errors = list(settings.errors)

    # On n'agit que s'il y a du nouveau : un mot de passe à appliquer, une erreur ou un
    # pays inconnu à signaler, un nom de Wi-Fi différent de celui déjà enregistré
    # (réseau ouvert), ou un autre pays. Sinon (cas normal après le premier démarrage),
    # on ne touche à rien.
    new_ssid = settings.ssid and settings.ssid != configured_ssid()
    new_country = settings.country and settings.country != current_regdomain()
    if not (
        settings.has_secrets() or errors or settings.country_invalid or new_ssid or new_country
    ):
        return [], [], []

    # Pays : jamais bloquant. Inconnu ou refusé -> réglage international.
    if settings.country:
        try:
            apply_country(settings.country)
            messages.append(f"Pays Wi-Fi : {settings.country}")
        except (subprocess.CalledProcessError, OSError, CmdlineError):
            warnings.append(
                f"pays « {settings.country} » refusé par le système : "
                "réglage Wi-Fi international utilisé"
            )
            apply_world_regdomain()
    else:
        apply_world_regdomain()

    if settings.ssh_password:
        try:
            apply_ssh_password(settings.ssh_password)
            messages.append(f"Mot de passe SSH de « {DEV_USER} » : enregistré")
        except subprocess.CalledProcessError:
            errors.append("impossible d'enregistrer le mot de passe SSH")

    # Wi-Fi : seulement s'il y a un mot de passe Wi-Fi ou un nouveau nom
    # (changer juste le pays ou le mot de passe SSH ne doit pas couper le Wi-Fi).
    if settings.ssid and (settings.psk or new_ssid):
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
    report += messages
    report += [f"ATTENTION : {w}" for w in warnings]
    report += [f"ERREUR : {e}" for e in errors]
    write_boot_file(
        path,
        wifi_file.render(
            ssid=values.get(wifi_file.KEY_SSID, ""),
            # un pays inconnu n'est pas recopié (sinon il serait signalé à chaque démarrage)
            country=settings.country or "",
            messages=report,
        ),
    )
    return messages, warnings, errors


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    path = BOOT_DIR / wifi_file.FILE_NAME
    state = load_state()

    # D'abord : cmdline.txt abîmé (ex. coupure de courant pendant une écriture) ?
    # Sans réparation, le prochain démarrage échouerait.
    repaired = repair_cmdline()

    if not path.exists():
        # Fichier supprimé : on remet un modèle vide pour pouvoir le remplir plus tard.
        write_boot_file(path, wifi_file.render())
        log.info("Modèle %s recréé.", path)
    else:
        try:
            messages, warnings, errors = apply_file(path)
        except Exception as exc:  # ne jamais bloquer le démarrage
            log.exception("Erreur pendant l'application de %s", path)
            messages, warnings, errors = [], [], [f"erreur inattendue : {exc}"]
        if messages or warnings or errors:
            state["last_applied"] = datetime.now().isoformat(timespec="seconds")
            state["messages"] = messages
            state["warnings"] = warnings
            state["errors"] = errors
        for m in messages:
            log.info("%s", m)
        for w in warnings + errors:
            log.warning("%s", w)

    # À chaque démarrage : radio Wi-Fi activée (même sans pays : réglage international),
    # puis on note l'état réel pour l'écran HDMI.
    if repaired:
        key = "errors" if "impossible" in repaired else "warnings"
        state[key] = list(state.get(key, [])) + [repaired]
    enable_wifi_radio()
    state["regdomain"] = current_regdomain()
    state["ssh_password_set"] = ssh_password_is_set()
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
