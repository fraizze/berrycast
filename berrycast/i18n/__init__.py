"""Traductions de l'interface (français par défaut, anglais disponible).

Utilisation :
    from berrycast.i18n import t, set_language
    set_language("en")
    t("ready")                                        # -> "Ready to receive"
    t("settings_address", url="http://tv-salon.local")

Les textes sont dans fr.json et en.json (une clé -> un texte). Si une clé manque
dans la langue choisie, on prend le français ; si elle manque aussi en français,
on renvoie la clé elle-même (l'écran affiche quelque chose plutôt que de planter).
"""

from __future__ import annotations

import json
import logging
from functools import cache
from pathlib import Path

log = logging.getLogger(__name__)

LANGUAGES = ("fr", "en")
DEFAULT_LANGUAGE = "fr"

_DIR = Path(__file__).parent
_current_language = DEFAULT_LANGUAGE


@cache
def load_messages(language: str) -> dict[str, str]:
    """Charge (une seule fois) le fichier de traduction d'une langue."""
    if language not in LANGUAGES:
        raise ValueError(f"Langue non prise en charge : {language!r}")
    with open(_DIR / f"{language}.json", encoding="utf-8") as f:
        return json.load(f)


def set_language(language: str) -> None:
    """Change la langue utilisée par t()."""
    global _current_language
    if language not in LANGUAGES:
        raise ValueError(f"Langue non prise en charge : {language!r}")
    _current_language = language


def get_language() -> str:
    """Langue actuellement utilisée par t()."""
    return _current_language


def t(key: str, language: str | None = None, **params: object) -> str:
    """Renvoie le texte traduit pour `key`, en remplaçant les {paramètres} éventuels."""
    language = language or _current_language
    text = load_messages(language).get(key)
    if text is None and language != DEFAULT_LANGUAGE:
        text = load_messages(DEFAULT_LANGUAGE).get(key)
    if text is None:
        log.warning("Traduction manquante : %r", key)
        return key
    if not params:
        return text
    try:
        return text.format(**params)
    except (KeyError, IndexError, ValueError) as exc:
        log.warning("Paramètre de traduction incorrect pour %r : %s", key, exc)
        return text
