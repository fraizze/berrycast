"""État des diffusions (Miracast, AirPlay), partagé avec l'écran HDMI.

Chaque source écrit son fichier dans /run/berrycast (effacé à chaque redémarrage) :
    /run/berrycast/miracast.json   /run/berrycast/airplay.json
Contenu :
    {"state": "ready" | "pin" | "connecting" | "casting" | "off",
     "pin": "1234 5678", "peer": "PC de Zoé", "updated": 1700000000.0}

- « ready »      : prêt, le code est affiché en petit sur l'écran d'accueil ;
- « pin »        : un appareil demande le code : l'écran l'affiche EN GRAND ;
- « connecting » : connexion en cours ;
- « casting »    : la vidéo occupe l'écran (l'écran texte ne dessine plus rien) ;
- « off »        : désactivé (réglages) ou service arrêté.

Règle « une seule diffusion à la fois » : une source ne démarre pas de diffusion si
l'autre est déjà en « casting » (voir other_is_casting).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

RUN_DIR = Path(os.environ.get("BERRYCAST_RUN_DIR", "/run/berrycast"))
SOURCES = ("miracast", "airplay")
STATES = ("ready", "pin", "connecting", "casting", "off")
STALE_SECONDS = 15  # un « casting » non rafraîchi depuis 15 s est considéré terminé


def _path(source: str, run_dir: Path | None = None) -> Path:
    if source not in SOURCES:
        raise ValueError(f"source inconnue : {source!r}")
    return (run_dir or RUN_DIR) / f"{source}.json"


def write(source: str, state: str, pin: str = "", peer: str = "",
          run_dir: Path | None = None, now: float | None = None) -> None:
    if state not in STATES:
        raise ValueError(f"état inconnu : {state!r}")
    path = _path(source, run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"state": state, "pin": pin, "peer": peer,
            "updated": time.time() if now is None else now}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def read(source: str, run_dir: Path | None = None, now: float | None = None) -> dict:
    """État d'une source ({} si inconnu). Un « casting » trop ancien redevient « ready »."""
    try:
        data = json.loads(_path(source, run_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    now = time.time() if now is None else now
    if data.get("state") == "casting" and now - float(data.get("updated", 0)) > STALE_SECONDS:
        data["state"] = "ready"  # service planté pendant une diffusion : on libère
    return data


def read_all(run_dir: Path | None = None, now: float | None = None) -> dict[str, dict]:
    return {source: read(source, run_dir, now) for source in SOURCES}


def other_is_casting(source: str, run_dir: Path | None = None, now: float | None = None) -> bool:
    return any(read(other, run_dir, now).get("state") == "casting"
               for other in SOURCES if other != source)


def other_wants_screen(source: str, run_dir: Path | None = None, now: float | None = None) -> bool:
    """L'autre source prépare ou fait une diffusion (« connecting » ou « casting »)."""
    return any(read(other, run_dir, now).get("state") in ("connecting", "casting")
               for other in SOURCES if other != source)


def wait_screen_free(source: str, timeout: float = 8.0, run_dir: Path | None = None,
                     sleep=time.sleep, clock=time.monotonic) -> bool:
    """Attend que l'autre source ait libéré l'écran (son état passe à « off »).

    Un seul programme à la fois peut piloter l'écran (« DRM master ») ; UxPlay le garde
    dès son démarrage, même sans diffusion : il faut l'arrêter avant de lancer la vidéo.
    """
    deadline = clock() + timeout
    while clock() < deadline:
        others = [read(o, run_dir) for o in SOURCES if o != source]
        if all(o.get("state") in (None, "off") for o in others):
            return True
        sleep(0.2)
    return False
