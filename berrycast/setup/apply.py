"""Application des réglages du premier lancement (partie root, la plus petite possible).

Échange entre l'interface (utilisateur « berrycast », sans droits) et cette partie :
1. l'interface écrit /run/berrycast-setup/request.json (dossier privé, effacé à l'arrêt) ;
2. systemd voit le fichier (berrycast-setup-apply.path) et lance ce programme en root ;
3. ce programme lit et EFFACE la demande, revérifie tout, applique, puis écrit
   /run/berrycast-setup/result.json que l'interface affiche.

Ce qui est appliqué : disposition du clavier (enregistrée), mot de passe de « pi »,
pays Wi-Fi, nom de l'appareil (config.toml), connexion au Wi-Fi.
Le nom d'hôte reste « berrycast » dans l'image de développement (berrycast.local).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from berrycast import config, countries
from berrycast.config import is_valid_device_name
from berrycast.dev import devsetup
from berrycast.dev.nm import split_terse
from berrycast.dev.wifi_file import is_valid_psk

log = logging.getLogger("berrycast.setup.apply")

RUN_DIR = Path(os.environ.get("BERRYCAST_SETUP_RUN", "/run/berrycast-setup"))
REQUEST = "request.json"
RESULT = "result.json"
KEYBOARD_FILE = Path("/etc/default/keyboard")
BOOT_DIR = Path(os.environ.get("BERRYCAST_BOOT_DIR", "/boot/firmware"))
FORCE_FILE = "berrycast-configurer.txt"  # voir autostart.py
MIN_PI_PASSWORD = 8
CONNECT_WAIT = 45  # secondes pour se connecter au Wi-Fi


# ---- Côté interface (sans droits) ---------------------------------------------


def submit(settings: dict, run_dir: Path = RUN_DIR, timeout: float = 150,
           poll: float = 0.5) -> dict:
    """Envoie la demande et attend le résultat (ou un résultat d'erreur si trop long)."""
    result_path = run_dir / RESULT
    result_path.unlink(missing_ok=True)
    tmp = run_dir / (REQUEST + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False)
    os.replace(tmp, run_dir / REQUEST)  # apparition « d'un coup » pour systemd

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result_path.exists():
            try:
                return json.loads(result_path.read_text(encoding="utf-8"))
            except ValueError:
                pass  # fichier en cours d'écriture
        time.sleep(poll)
    return {"ok": False, "error": "timeout"}


# ---- Côté root ------------------------------------------------------------------


def validate(req: dict) -> list[str]:
    """Revérifie la demande (on ne fait jamais confiance au côté sans droits)."""
    errors = []
    if not is_valid_device_name(req.get("device_name")):
        errors.append("nom de l'appareil invalide")
    ssid = req.get("ssid") or ""
    if not ssid or len(ssid.encode()) > 32:
        errors.append("nom du Wi-Fi invalide")
    psk = req.get("psk") or ""
    if psk and not is_valid_psk(psk):
        errors.append("mot de passe Wi-Fi invalide")
    pw = req.get("pi_password") or ""
    if len(pw) < MIN_PI_PASSWORD or ":" in pw or "\n" in pw:
        errors.append("mot de passe de pi invalide")
    layout = req.get("keyboard_layout") or ""
    variant = req.get("keyboard_variant") or ""
    if not (layout.isalpha() and len(layout) <= 8) or not (variant == "" or variant.isalnum()):
        errors.append("disposition du clavier invalide")
    country = req.get("country")
    if country is not None and countries.normalize_country(country) is None:
        errors.append("pays invalide")
    return errors


def update_keyboard_file(text: str, layout: str, variant: str) -> str:
    """Remplace XKBLAYOUT / XKBVARIANT dans le contenu de /etc/default/keyboard."""
    values = {"XKBLAYOUT": layout, "XKBVARIANT": variant}
    lines, seen = [], set()
    for line in text.splitlines():
        key = line.split("=", 1)[0].strip()
        if key in values:
            lines.append(f'{key}="{values[key]}"')
            seen.add(key)
        else:
            lines.append(line)
    lines += [f'{k}="{v}"' for k, v in values.items() if k not in seen]
    return "\n".join(lines) + "\n"


def save_keyboard(layout: str, variant: str) -> None:
    try:
        text = KEYBOARD_FILE.read_text(encoding="utf-8")
    except OSError:
        text = ""
    KEYBOARD_FILE.write_text(update_keyboard_file(text, layout, variant), encoding="utf-8")


def wifi_ip() -> str:
    out = devsetup.run(["nmcli", "-g", "IP4.ADDRESS", "device", "show", "wlan0"],
                       check=False).stdout.strip()
    return out.split("|")[0].strip().split("/")[0] if out else ""


def explain_failure(nm_error: str) -> str:
    """Message compréhensible à partir de l'erreur de NetworkManager."""
    text = nm_error.lower()
    if "secrets were required" in text or "802-1x" in text or "psk" in text:
        return "wrong_password"
    if "no network with ssid" in text or "could not be found" in text or "not found" in text:
        return "not_found"
    return "failed"


def apply_keyboard_only(req: dict) -> dict:
    """Demande « clavier seul » : charger la disposition sur tty1 et l'enregistrer."""
    from berrycast.setup.keyboards import Layout, is_safe
    from berrycast.setup.keyboards import apply as load_layout

    layout, variant = req.get("keyboard_layout") or "", req.get("keyboard_variant") or ""
    if not is_safe(layout, variant):
        return {"ok": False, "error": "invalid", "details": ["disposition invalide"]}
    ok, error = load_layout(Layout(layout, layout, variant), console="/dev/tty1")
    save_keyboard(layout, variant)
    return {"ok": ok, "details": [error] if error else []}


def apply(req: dict) -> dict:
    if req.get("action") == "keyboard":
        return apply_keyboard_only(req)
    errors = validate(req)
    if errors:
        return {"ok": False, "error": "invalid", "details": errors}

    warnings: list[str] = []
    save_keyboard(req["keyboard_layout"], req.get("keyboard_variant") or "")
    devsetup.apply_ssh_password(req["pi_password"])

    country = req.get("country")
    if country:
        try:
            devsetup.apply_country(country)
        except subprocess.CalledProcessError:
            warnings.append("country_refused")
            devsetup.apply_world_regdomain()
    else:
        devsetup.apply_world_regdomain()

    cfg = config.load()
    cfg.device_name = req["device_name"].strip()
    config.save(cfg)

    devsetup.enable_wifi_radio()
    devsetup.wait_for_wifi_device()
    ok, nm_error = devsetup.connect_wifi(req["ssid"], req.get("psk") or None, CONNECT_WAIT)
    if not ok:
        log.warning("Connexion Wi-Fi impossible : %s", nm_error)
        return {"ok": False, "error": explain_failure(nm_error), "details": [nm_error],
                "warnings": warnings}

    cfg.setup_done = True
    config.save(cfg)
    # Configuration forcée par fichier (voir autostart.py) : terminée, on retire le fichier
    (BOOT_DIR / FORCE_FILE).unlink(missing_ok=True)
    return {"ok": True, "ip": wifi_ip(), "warnings": warnings}


def refresh_screen_status() -> None:
    """Met à jour l'état lu par l'écran « BerryCast dev » (pays Wi-Fi, mot de passe de pi).

    Sans cela, l'écran garderait l'état du démarrage (avant la configuration).
    Les anciens messages de berrycast-wifi.txt sont effacés : ils ne sont plus d'actualité.
    """
    state = devsetup.load_state()
    state["ssh_password_set"] = devsetup.ssh_password_is_set()
    state["regdomain"] = devsetup.current_regdomain()
    state["errors"], state["warnings"], state["messages"] = [], [], []
    devsetup.save_state(state)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    request_path = RUN_DIR / REQUEST
    try:
        req = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.error("Demande illisible : %s", exc)
        req = None
    finally:
        request_path.unlink(missing_ok=True)  # contient des mots de passe : effacée tout de suite

    try:
        result = apply(req) if isinstance(req, dict) else {"ok": False, "error": "invalid"}
    except Exception as exc:  # toujours répondre à l'interface
        log.exception("Erreur pendant l'application")
        result = {"ok": False, "error": "failed", "details": [str(exc)]}

    try:
        refresh_screen_status()
    except Exception:  # l'écran est secondaire : ne jamais bloquer la réponse
        log.exception("État de l'écran non mis à jour")

    tmp = RUN_DIR / (RESULT + ".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, RUN_DIR / RESULT)
    log.info("Résultat : %s", "OK" if result.get("ok") else result.get("error"))
    return 0


def wifi_connected() -> bool:
    """Vrai si le Wi-Fi (wlan0) est connecté (utilisé aussi au démarrage)."""
    try:
        out = subprocess.run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    for line in out.splitlines():
        fields = split_terse(line)
        if len(fields) >= 3 and fields[1] == "wifi" and fields[2] == "connected":
            return True
    return False


if __name__ == "__main__":
    sys.exit(main())
