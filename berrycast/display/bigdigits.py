"""Gros chiffres pour la console (codes PIN lisibles de loin), dessinés avec « █ ».

Le caractère « █ » (U+2588) existe dans les polices console latines (Lat15, Terminus).
Chaque chiffre fait 5 colonnes sur 5 lignes ; une espace dans le texte = petit espace.
"""

from __future__ import annotations

BLOCK = "█"

FONT = {
    "0": ("#####", "#   #", "#   #", "#   #", "#####"),
    "1": ("  #  ", " ##  ", "  #  ", "  #  ", " ### "),
    "2": ("#####", "    #", "#####", "#    ", "#####"),
    "3": ("#####", "    #", " ####", "    #", "#####"),
    "4": ("#   #", "#   #", "#####", "    #", "    #"),
    "5": ("#####", "#    ", "#####", "    #", "#####"),
    "6": ("#####", "#    ", "#####", "#   #", "#####"),
    "7": ("#####", "    #", "   # ", "  #  ", "  #  "),
    "8": ("#####", "#   #", "#####", "#   #", "#####"),
    "9": ("#####", "#   #", "#####", "    #", "#####"),
    " ": ("  ", "  ", "  ", "  ", "  "),
}
HEIGHT = 5


def render(text: str, gap: int = 1) -> list[str]:
    """Lignes du texte en gros (seuls les chiffres et les espaces sont dessinés)."""
    glyphs = [FONT[ch] for ch in text if ch in FONT]
    # Toutes les lignes ont la même largeur : centrées ligne par ligne, elles restent alignées
    return [(" " * gap).join(g[row] for g in glyphs).replace("#", BLOCK)
            for row in range(HEIGHT)]


def width(text: str, gap: int = 1) -> int:
    return max((len(line) for line in render(text, gap)), default=0)
