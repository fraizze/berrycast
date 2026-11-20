"""État du mode configuration, partagé entre le service de configuration et l'écran HDMI.

Fichier /run/berrycast/setup.json (effacé à chaque redémarrage). Il contient le nom du
Wi-Fi temporaire, son mot de passe et le code de vérification : ce sont précisément les
informations affichées sur la TV ; elles ne servent que pendant la configuration.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

STATE_FILE = Path(os.environ.get("BERRYCAST_RUN_DIR", "/run/berrycast")) / "setup.json"


def write(state: dict, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def read(path: Path = STATE_FILE) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def clear(path: Path = STATE_FILE) -> None:
    path.unlink(missing_ok=True)
