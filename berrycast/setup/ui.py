"""Interface graphique du premier lancement, sur la TV (pygame en plein écran, sans bureau).

- Affichage : pygame / SDL2 avec le pilote « kmsdrm » (écran HDMI directement, sans X).
- Clavier : lu sur la console tty1 (berrycast.setup.keys), qui applique la disposition
  choisie (suisse, français…). systemd donne tty1 au programme (StandardInput=tty).
- Style : fond noir, texte blanc, sobre ; polices DejaVu (lisses), champs arrondis.

Affichage OPTIONNEL (BERRYCAST_SETUP_DISPLAY=graphique) : l'affichage par défaut est
le texte (console_ui), qui fonctionne partout. Lancement : berrycast.setup.main.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from berrycast.i18n import t
from berrycast.setup.form import Row
from berrycast.setup.session import Session

BG = (0, 0, 0)
FG = (255, 255, 255)
MUTED = (150, 150, 150)
FIELD = (20, 20, 20)
FIELD_FOCUS = (34, 34, 34)
LINE = (70, 70, 70)
ERROR = (255, 138, 128)
OK = (126, 226, 168)

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


class Theme:
    """Tailles proportionnelles à la hauteur de l'écran (référence : 1080 lignes)."""

    def __init__(self, pygame, height: int):
        s = height / 1080
        self.s = s
        self.pad = round(24 * s)
        self.radius = round(14 * s)
        self.row_h = round(62 * s)
        self.gap = round(12 * s)
        self.title = self._font(pygame, 54 * s, bold=True)
        self.subtitle = self._font(pygame, 28 * s)
        self.label = self._font(pygame, 28 * s)
        self.value = self._font(pygame, 32 * s)
        self.button = self._font(pygame, 32 * s, bold=True)
        self.small = self._font(pygame, 22 * s)

    @staticmethod
    def _font(pygame, size: float, bold: bool = False):
        # BERRYCAST_FONT(_BOLD) : autre police (aperçu sur PC, par exemple)
        override = os.environ.get("BERRYCAST_FONT_BOLD" if bold else "BERRYCAST_FONT")
        path = Path(override) if override else FONT_DIR / (
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
        if path.exists():
            return pygame.font.Font(str(path), max(10, round(size)))
        font = pygame.font.Font(None, max(10, round(size * 1.3)))
        font.set_bold(bold)
        return font


def fit(font, text: str, max_width: int) -> str:
    """Raccourcit le texte avec « … » s'il dépasse la largeur."""
    if font.size(text)[0] <= max_width:
        return text
    while text and font.size(text + "…")[0] > max_width:
        text = text[:-1]
    return text + "…"


class SetupUI:
    def __init__(self, pygame, screen, session: Session):
        self.pg = pygame
        self.screen = screen
        self.session = session
        self.form = session.form
        self.w, self.h = screen.get_size()
        self.theme = Theme(pygame, self.h)

    # ---- Dessin -------------------------------------------------------------

    def text(self, font, text, color, x, y, center=False):
        surface = font.render(text, True, color)
        rect = surface.get_rect()
        if center:
            rect.midtop = (x, y)
        else:
            rect.topleft = (x, y)
        self.screen.blit(surface, rect)
        return rect

    def box(self, rect, fill, border=None, width=2):
        self.pg.draw.rect(self.screen, fill, rect, border_radius=self.theme.radius)
        if border:
            self.pg.draw.rect(self.screen, border, rect, width=width,
                              border_radius=self.theme.radius)

    def content_rect(self):
        th = self.theme
        width = min(round(self.w * 0.84), round(1200 * th.s))
        return (self.w - width) // 2, width

    def draw(self) -> None:
        self.screen.fill(BG)
        session = self.session
        if session.state == "applying":
            ssid = self.form.result()["ssid"]
            self.draw_message(t("setup_applying", ssid=ssid), [t("setup_applying_hint")])
        elif session.state == "done":
            ip = session.result.get("ip") or "?"
            self.draw_message(t("setup_done_title"), [
                t("setup_done_wifi", ssid=self.form.result()["ssid"]),
                t("setup_done_ip", ip=ip),
                t("setup_done_ssh", ip=ip),
                "",
                t("setup_done_keys"),
            ], title_color=OK)
        else:
            self.draw_form()
            if self.form.dropdown:
                self.draw_dropdown()
            footer = session.busy or (session.notice if session.notice_visible() else "")
            if footer:
                self.text(self.theme.small, footer, OK, self.w // 2,
                          self.h - round(100 * self.theme.s), center=True)
        self.pg.display.flip()

    def draw_message(self, title: str, lines: list[str], title_color=FG) -> None:
        th = self.theme
        total = th.title.get_linesize() + round(30 * th.s) + len(lines) * th.row_h
        y = (self.h - total) // 2
        self.text(th.title, title, title_color, self.w // 2, y, center=True)
        y += th.title.get_linesize() + round(30 * th.s)
        for line in lines:
            self.text(th.value, line, MUTED if line == lines[-1] else FG, self.w // 2, y,
                      center=True)
            y += th.row_h

    def draw_header(self, title, subtitle) -> int:
        th = self.theme
        y = round(50 * th.s)
        self.text(th.title, title, FG, self.w // 2, y, center=True)
        y += th.title.get_linesize() + round(4 * th.s)
        self.text(th.subtitle, subtitle, MUTED, self.w // 2, y, center=True)
        return y + th.subtitle.get_linesize() + round(28 * th.s)

    def draw_form(self) -> None:
        th = self.theme
        top = self.draw_header(t("setup_title"), t("setup_subtitle"))
        if self.session.error:
            self.text(th.label, self.session.error, ERROR, self.w // 2, top - round(10 * th.s),
                      center=True)
            top += th.label.get_linesize() + round(10 * th.s)
        left, width = self.content_rect()
        label_w = round(width * 0.36)
        rows = self.form.rows
        heights = [th.row_h + (th.small.get_linesize() if r.error else 0) for r in rows]
        bottom_limit = self.h - round(90 * th.s)

        # Défilement : la ligne choisie reste visible si tout ne tient pas
        offset = 0
        focus_bottom = top + sum(h + th.gap for h in heights[: self.form.focus + 1])
        if focus_bottom > bottom_limit:
            offset = focus_bottom - bottom_limit

        y = top - offset
        for i, (row, height) in enumerate(zip(rows, heights, strict=True)):
            if y + th.row_h > top - th.gap and y < bottom_limit:
                self.draw_row(row, i == self.form.focus, left, y, width, label_w)
            y += height + th.gap

        help_y = self.h - round(60 * th.s)
        self.text(th.small, t("setup_help"), MUTED, self.w // 2, help_y, center=True)

    def draw_row(self, row: Row, focused: bool, left, y, width, label_w) -> None:
        pg, th = self.pg, self.theme
        if row.kind == "button":
            rect = pg.Rect(left, y, width, th.row_h)
            primary = row.key == "submit"
            if focused:
                self.box(rect, FG if primary else FIELD_FOCUS, FG, 3)
                color = BG if primary else FG
            else:
                self.box(rect, FIELD, LINE)
                color = FG
            font = th.button if primary else th.value
            ty = y + (th.row_h - font.get_linesize()) // 2
            self.text(font, row.value, color, rect.centerx, ty, center=True)
            return

        label_y = y + (th.row_h - th.label.get_linesize()) // 2
        self.text(th.label, fit(th.label, row.label, label_w - th.pad), FG if focused else MUTED,
                  left, label_y)
        rect = pg.Rect(left + label_w, y, width - label_w, th.row_h)
        self.box(rect, FIELD_FOCUS if focused else FIELD, FG if focused else LINE,
                 3 if focused else 2)

        value = row.display_value(self.form.show_passwords)
        color = FG if (row.value or row.kind != "choice") else MUTED
        arrows_w = round(70 * th.s) if row.kind == "choice" else 0
        inner_w = rect.width - 2 * th.pad - arrows_w
        shown = fit(th.value, value, inner_w)
        vy = y + (th.row_h - th.value.get_linesize()) // 2
        text_rect = self.text(th.value, shown, color, rect.x + th.pad, vy)

        if focused and row.kind in ("text", "password") and int(time.monotonic() * 2) % 2 == 0:
            cx = text_rect.right + round(3 * th.s)
            pg.draw.line(self.screen, FG, (cx, vy + round(4 * th.s)),
                         (cx, vy + th.value.get_linesize() - round(4 * th.s)), 2)
        if row.kind == "choice":
            self.draw_chevrons(rect, focused)
        if row.error:
            self.text(th.small, row.error, ERROR, rect.x + th.pad,
                      y + th.row_h + round(2 * th.s))

    def draw_chevrons(self, rect, focused: bool) -> None:
        """Petits triangles dessinés (indépendants de la police) : ◂ ▸ si choisi, sinon ▾."""
        s = self.theme.s
        size = round(9 * s)
        cy = rect.centery
        right = rect.right - self.theme.pad
        if focused:
            for cx, direction in ((right - round(42 * s), -1), (right - size, 1)):
                tip = cx + direction * size
                points = [(tip, cy), (cx - direction * size // 2, cy - size),
                          (cx - direction * size // 2, cy + size)]
                self.pg.draw.polygon(self.screen, FG, points)
        else:
            cx = right - size
            points = [(cx - size, cy - size // 2), (cx + size, cy - size // 2),
                      (cx, cy + size)]
            self.pg.draw.polygon(self.screen, MUTED, points)

    def draw_dropdown(self) -> None:
        pg, th = self.pg, self.theme
        dd = self.form.dropdown
        veil = pg.Surface((self.w, self.h), pg.SRCALPHA)
        veil.fill((0, 0, 0, 200))
        self.screen.blit(veil, (0, 0))

        left, width = self.content_rect()
        visible = 9
        item_h = round(56 * th.s)
        panel_h = th.label.get_linesize() + 2 * th.pad + visible * item_h + th.pad
        panel = pg.Rect(left + width // 8, (self.h - panel_h) // 2, width * 3 // 4, panel_h)
        self.box(panel, (12, 12, 12), FG, 2)
        self.text(th.label, dd.row.label, MUTED, panel.x + th.pad, panel.y + th.pad)

        options = dd.row.options
        start = max(0, min(dd.index - visible // 2, len(options) - visible))
        y = panel.y + th.pad + th.label.get_linesize() + th.pad // 2
        for i in range(start, min(start + visible, len(options))):
            item = pg.Rect(panel.x + th.pad // 2, y, panel.width - th.pad, item_h - 4)
            selected = i == dd.index
            if selected:
                self.box(item, FG)
            label = fit(th.value, options[i][1], item.width - 2 * th.pad)
            ty = y + (item_h - th.value.get_linesize()) // 2
            self.text(th.value, label, BG if selected else FG, item.x + th.pad, ty)
            y += item_h
        self.text(th.small, t("setup_help_dropdown"), MUTED, self.w // 2,
                  panel.bottom + round(16 * th.s), center=True)
