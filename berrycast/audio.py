"""Choix de la sortie son ALSA (HDMI ou prise jack) du Raspberry Pi.

Sur Raspberry Pi OS (pilote vc4), les cartes son s'appellent par exemple
« vc4hdmi » (HDMI) et « Headphones » (prise jack 3,5 mm). On lit /proc/asound/cards
pour trouver la bonne, plutôt que de supposer un numéro de carte.
"""

from __future__ import annotations

import re
from pathlib import Path

CARDS_FILE = Path("/proc/asound/cards")


def parse_cards(text: str) -> list[tuple[int, str, str]]:
    """(numéro, identifiant, description) de chaque carte de /proc/asound/cards.

    Exemple de ligne : « 1 [vc4hdmi        ]: vc4-hdmi - vc4-hdmi »
    """
    cards = []
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\s+\[(\S+)\s*\]:\s*(.*)", line)
        if m:
            cards.append((int(m.group(1)), m.group(2), m.group(3).strip()))
    return cards


def alsa_device(output: str = "hdmi", cards_text: str | None = None) -> str | None:
    """Périphérique ALSA (« plughw:CARD=vc4hdmi,DEV=0 ») pour « hdmi » ou « jack ».

    None si aucune carte ne correspond : on laissera alors ALSA choisir.
    """
    if cards_text is None:
        try:
            cards_text = CARDS_FILE.read_text(encoding="utf-8")
        except OSError:
            return None
    wanted = ("hdmi",) if output == "hdmi" else ("headphones", "jack", "bcm2835")
    for _, card_id, desc in parse_cards(cards_text):
        name = (card_id + " " + desc).lower()
        if any(w in name for w in wanted) and not (output == "jack" and "hdmi" in name):
            return f"plughw:CARD={card_id},DEV=0"
    return None
