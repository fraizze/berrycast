"""Interface graphique du premier lancement, sur la TV (pygame en plein écran, sans bureau).

- Affichage : pygame / SDL2 avec le pilote « kmsdrm » (écran HDMI directement, sans X).
- Clavier : lu sur la console tty1 (berrycast.setup.keys), qui applique la disposition
  choisie (suisse, français…). systemd donne tty1 au programme (StandardInput=tty).
- Style : fond noir, texte blanc, sobre ; polices DejaVu (lisses), champs arrondis.

Étape 1 du développement : le formulaire complet, sans encore appliquer les réglages
(un écran récapitulatif s'affiche à la fin).

Lancement (sur le Pi, voir la procédure de test) : python3 -m berrycast.setup.ui
"""

from __future__ import annotations

import os
import select
import sys
import time
from pathlib import Path

from berrycast import countries
from berrycast.i18n import t
from berrycast.setup import keyboards, wifi
from berrycast.setup.form import APPLY_KEYBOARD, QUIT, REFRESH, SUBMITTED, Row, SetupForm
from berrycast.setup.keys import KeyDecoder

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
    def __init__(self, pygame, screen, form: SetupForm):
        self.pg = pygame
        self.screen = screen
        self.form = form
        self.w, self.h = screen.get_size()
        self.theme = Theme(pygame, self.h)
        self.mode = "form"  # "form" ou "summary"
        self.notice = ""
        self.notice_until = 0.0

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
        if self.mode == "summary":
            self.draw_summary()
        else:
            self.draw_form()
            if self.form.dropdown:
                self.draw_dropdown()
        if self.notice and time.monotonic() < self.notice_until:
            self.text(self.theme.small, self.notice, OK, self.w // 2,
                      self.h - round(100 * self.theme.s), center=True)
        self.pg.display.flip()

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

        value = row.display_value()
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

    def draw_summary(self) -> None:
        th = self.theme
        top = self.draw_header(t("setup_summary_title"), t("setup_summary_next"))
        left, width = self.content_rect()
        res = self.form.result()
        names = dict(self.form.rows_by_key["country"].options)
        lines = [
            (t("setup_keyboard"), res["keyboard"].label),
            (t("setup_name"), res["device_name"]),
            (t("setup_wifi"), res["ssid"]),
            (t("setup_wifi_password"), "•" * len(res["psk"]) if res["psk"] else "—"),
            (t("setup_country"), names.get(res["country"], t("setup_country_none"))),
            (t("setup_pi_password"), "•" * len(res["pi_password"])),
        ]
        y = top
        for label, value in lines:
            self.text(th.label, label, MUTED, left, y)
            self.text(th.value, fit(th.value, value, round(width * 0.6)), FG,
                      left + round(width * 0.38), y)
            y += th.row_h
        self.text(th.small, t("setup_summary_keys"), MUTED, self.w // 2,
                  self.h - round(60 * th.s), center=True)

    # ---- Actions ----------------------------------------------------------------

    def notify(self, message: str, seconds: float = 4) -> None:
        self.notice = message
        self.notice_until = time.monotonic() + seconds

    def apply_keyboard(self) -> None:
        layout = keyboards.LAYOUTS[int(self.form.rows_by_key["keyboard"].value)]
        if not keyboards.apply(layout):
            self.notify(t("setup_keyboard_failed"))

    def refresh(self) -> None:
        self.notify(t("setup_refreshing"), seconds=30)
        self.draw()
        self.form.set_networks(wifi.scan(rescan=True))
        self.notice_until = 0

    def handle(self, kind: str, value: str) -> bool:
        """Traite une touche. Renvoie False pour quitter."""
        if self.mode == "summary":
            if kind == "key" and value == "esc":
                self.mode = "form"
            elif kind == "key" and value in ("enter", "ctrl-c"):
                return False
            return True
        action = self.form.handle(kind, value)
        if action == APPLY_KEYBOARD:
            self.apply_keyboard()
        elif action == REFRESH:
            self.refresh()
        elif action == SUBMITTED:
            self.mode = "summary"
        elif action == QUIT:
            return False
        return True


def build_form() -> SetupForm:
    detected = wifi.detect_country()
    names = countries.country_names("fr")
    return SetupForm(
        networks=wifi.scan(),
        countries=countries.sorted_countries(names, first=detected),
        detected_country=detected,
        keyboard_index=keyboards.default_index(detected),
    )


def main() -> int:
    os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame

    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
    print(f"Écran {screen.get_size()[0]}x{screen.get_size()[1]}, pilote "
          f"{pygame.display.get_driver()}", file=sys.stderr)

    form = build_form()
    ui = SetupUI(pygame, screen, form)
    ui.apply_keyboard()  # disposition proposée appliquée tout de suite

    fd = sys.stdin.fileno()
    saved = None
    if os.isatty(fd):
        import termios
        import tty

        saved = termios.tcgetattr(fd)
        tty.setraw(fd)  # chaque touche arrive tout de suite, sans écho
    else:
        print("Clavier : l'entrée standard n'est pas un terminal "
              "(lancer avec StandardInput=tty).", file=sys.stderr)

    decoder = KeyDecoder()
    running = True
    last_tick = None
    try:
        while running:
            ready, _, _ = select.select([fd], [], [], 0.05)
            data = os.read(fd, 1024) if ready else b""
            events = decoder.feed(data, final=not ready)
            for kind, value in events:
                running = ui.handle(kind, value)
                if not running:
                    break
            pygame.event.pump()
            # On ne redessine que si nécessaire (touche, clignotement du curseur, message) :
            # le Pi 3 dessine en logiciel, un écran 1080p complet coûte cher.
            tick = (int(time.monotonic() * 2), time.monotonic() < ui.notice_until)
            if events or tick != last_tick:
                ui.draw()
                last_tick = tick
    finally:
        if saved is not None:
            import termios

            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        pygame.quit()
    if ui.mode == "summary":
        res = form.result()
        print(f"Réglages saisis : clavier={res['keyboard'].label!r}, nom={res['device_name']!r}, "
              f"wifi={res['ssid']!r}, pays={res['country']!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
