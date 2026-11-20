"""Lecture du clavier depuis la console tty1 (sans serveur graphique).

On lit les octets envoyés par le terminal : le noyau a déjà appliqué la disposition
du clavier (suisse, français…), donc les lettres et les accents arrivent corrects.
Les touches spéciales arrivent sous forme de séquences « Échap [ … ».
"""

from __future__ import annotations

import codecs

# Séquences de la console Linux -> nom de touche
SEQUENCES = {
    "\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
    "\x1b[5~": "pgup", "\x1b[6~": "pgdn",
    "\x1b[1~": "home", "\x1b[H": "home", "\x1b[4~": "end", "\x1b[F": "end",
    "\x1b[3~": "delete", "\x1b[2~": "insert",
    "\x1b[[E": "f5", "\x1b[15~": "f5",
}
SINGLE = {
    "\r": "enter", "\n": "enter", "\t": "tab", "\x7f": "backspace", "\x08": "backspace",
    "\x03": "ctrl-c",
}


class KeyDecoder:
    """Transforme des octets bruts en événements : ("key", "up") ou ("char", "é")."""

    def __init__(self) -> None:
        self._utf8 = codecs.getincrementaldecoder("utf-8")(errors="ignore")
        self._pending = ""

    def feed(self, data: bytes, final: bool = False) -> list[tuple[str, str]]:
        """`final=True` quand plus rien n'arrive : une « Échap » seule est alors une touche."""
        self._pending += self._utf8.decode(data)
        events: list[tuple[str, str]] = []
        text = self._pending
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\x1b":
                rest = text[i:]
                match = next((s for s in SEQUENCES if rest.startswith(s)), None)
                if match:
                    events.append(("key", SEQUENCES[match]))
                    i += len(match)
                    continue
                if any(s.startswith(rest) for s in SEQUENCES) and not final:
                    break  # séquence incomplète : on attend la suite
                if len(rest) > 1 and rest[1] == "[":
                    # séquence inconnue : on l'ignore jusqu'à sa lettre finale
                    j = 2
                    while j < len(rest) and not (rest[j].isalpha() or rest[j] == "~"):
                        j += 1
                    i += j + 1
                    continue
                events.append(("key", "esc"))
                i += 1
            elif ch in SINGLE:
                events.append(("key", SINGLE[ch]))
                i += 1
            elif ch.isprintable():
                events.append(("char", ch))
                i += 1
            else:
                i += 1  # autre caractère de contrôle : ignoré
        self._pending = text[i:]
        return events
