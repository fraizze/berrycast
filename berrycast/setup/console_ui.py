"""Affichage TEXTE du premier lancement, sur la console tty1 (affichage par défaut).

Même formulaire que la version graphique, dessiné avec du texte : fond noir, texte
blanc, grande police Terminus, ligne choisie en surbrillance (vidéo inversée).
C'est le même chemin d'affichage que l'écran « BerryCast dev » : il fonctionne sur
toutes les TV, sans pilote graphique.
"""

from __future__ import annotations

from berrycast.i18n import t
from berrycast.setup.form import Row
from berrycast.setup.session import Session

CLEAR = "\033[0m\033[2J\033[H"
HIDE_CURSOR = "\033[?25l"
NO_BLANKING = "\033[9;0]"
BOLD, REVERSE, RED, GREEN, DIM, RESET = (
    "\033[1m", "\033[7m", "\033[31;1m", "\033[32;1m", "\033[37m", "\033[0m")

LABEL_WIDTH = 28
MAX_WIDTH = 96
LEFT, RIGHT = "◀", "▶"  # ◀ ▶ (présents dans la police Lat15)


def _clip(text: str, width: int) -> str:
    if width <= 0:
        return ""
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"


def _field(row: Row, focused: bool, width: int) -> str:
    """Valeur d'un champ, sur `width` colonnes exactement : 2 colonnes, valeur, 1 colonne."""
    value = row.display_value()
    if row.kind == "choice":
        prefix, suffix = (LEFT + " " if focused else "  "), RIGHT
    else:
        prefix, suffix = "  ", " "
        if focused:
            value += "_"  # curseur
    text = prefix + _clip(value, width - 3).ljust(width - 3) + suffix
    return f"{REVERSE}{text}{RESET}" if focused else text


def _console_glyphs(text: str) -> str:
    """La police console (Lat15) n'a pas ← → : on utilise ◀ ▶ à la place."""
    return text.replace("←", LEFT).replace("→", RIGHT)


class Screen:
    """Construit l'écran complet (chaîne de caractères avec positions absolues)."""

    def __init__(self, cols: int, rows: int):
        self.cols, self.rows = cols, rows
        self.parts: list[str] = [CLEAR, HIDE_CURSOR, NO_BLANKING]

    def put(self, row: int, col: int, text: str) -> None:
        if 0 <= row < self.rows:
            self.parts.append(f"\033[{row + 1};{max(0, col) + 1}H{text}")

    def center(self, row: int, text: str, style: str = "", visible_len: int | None = None):
        length = len(text) if visible_len is None else visible_len
        self.put(row, (self.cols - length) // 2, f"{style}{text}{RESET}" if style else text)

    def render(self) -> str:
        return "".join(self.parts)


def render(session: Session, cols: int, rows: int) -> str:
    screen = Screen(cols, rows)
    width = min(MAX_WIDTH, cols - 4)
    left = (cols - width) // 2

    if session.state == "applying":
        ssid = session.form.result()["ssid"]
        mid = rows // 2 - 2
        screen.center(mid, t("setup_applying", ssid=ssid), BOLD)
        screen.center(mid + 2, t("setup_applying_hint"))
        return screen.render()

    if session.state == "done":
        ip = session.result.get("ip") or "?"
        lines = [
            (t("setup_done_title"), GREEN),
            ("", ""),
            (t("setup_done_wifi", ssid=session.form.result()["ssid"]), ""),
            (t("setup_done_ip", ip=ip), ""),
            (t("setup_done_ssh", ip=ip), ""),
            ("", ""),
            (t("setup_done_keys"), DIM),
        ]
        top = (rows - len(lines)) // 2
        for i, (text, style) in enumerate(lines):
            screen.center(top + i, text, style)
        return screen.render()

    # Formulaire
    form = session.form
    lines: list[tuple[str, int]] = []  # (texte, index de ligne du formulaire)
    for i, row in enumerate(form.rows):
        focused = i == form.focus
        if row.kind == "button":
            label = f"[ {row.value} ]"
            pad = (width - len(label)) // 2
            text = " " * pad + (f"{REVERSE}{label}{RESET}" if focused else label)
            lines.append((text, i))
        else:
            name = _clip(row.label, LABEL_WIDTH - 2).ljust(LABEL_WIDTH)
            name = f"{BOLD}{name}{RESET}" if focused else name
            lines.append((name + _field(row, focused, width - LABEL_WIDTH), i))
        if row.error:
            error = _clip(row.error, width - LABEL_WIDTH)
            lines.append((" " * LABEL_WIDTH + f"{RED}{error}{RESET}", i))

    # En-tête + formulaire centrés verticalement (titre, sous-titre, erreur éventuelle)
    header = 4 + (2 if session.error else 0)
    y = max(1, (rows - 3 - header - len(lines)) // 2)
    screen.center(y, t("setup_title"), BOLD)
    screen.center(y + 1, t("setup_subtitle"), DIM)
    y += 3
    if session.error:
        screen.center(y, _clip(session.error, width), RED)
        y += 2

    # Défilement si l'écran est trop petit : la ligne choisie reste visible
    available = rows - y - 3
    focus_lines = [n for n, (_, i) in enumerate(lines) if i == form.focus]
    first = 0
    if len(lines) > available and focus_lines:
        first = max(0, min(focus_lines[-1] - available + 1, len(lines) - available))
    for n, (text, _) in enumerate(lines[first:first + available]):
        screen.put(y + n, left, text)

    footer = session.busy or (session.notice if session.notice_visible() else "")
    if footer:
        screen.center(rows - 3, _clip(footer, width), GREEN)
    help_text = _console_glyphs(t("setup_help_dropdown") if form.dropdown else t("setup_help"))
    screen.center(rows - 2, _clip(help_text, cols - 2), DIM)

    if form.dropdown:
        _render_dropdown(screen, session, width)
    return screen.render()


def _render_dropdown(screen: Screen, session: Session, width: int) -> None:
    dd = session.form.dropdown
    options = dd.row.options
    box_w = min(width - 8, 70)
    visible = min(len(options), max(3, screen.rows - 10))
    box_h = visible + 4
    top = (screen.rows - box_h) // 2
    left = (screen.cols - box_w) // 2
    inner = box_w - 2

    screen.put(top, left, "┌" + "─" * inner + "┐")
    title = f" {_clip(dd.row.label, inner - 2)}".ljust(inner)
    screen.put(top + 1, left, f"│{BOLD}{title}{RESET}│")
    screen.put(top + 2, left, "├" + "─" * inner + "┤")
    start = max(0, min(dd.index - visible // 2, len(options) - visible))
    for n, i in enumerate(range(start, start + visible)):
        text = f" {_clip(options[i][1], inner - 2)}".ljust(inner)
        if i == dd.index:
            text = f"{REVERSE}{text}{RESET}"
        screen.put(top + 3 + n, left, f"│{text}│")
    screen.put(top + 3 + visible, left, "└" + "─" * inner + "┘")


def terminal_size(fd: int) -> tuple[int, int]:
    import fcntl
    import struct
    import termios

    try:
        rows, cols, _, _ = struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))
        if rows and cols:
            return cols, rows
    except OSError:
        pass
    return 80, 25
