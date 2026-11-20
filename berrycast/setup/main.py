"""Point d'entrée du premier lancement : python3 -m berrycast.setup.main

Affichage choisi par la variable BERRYCAST_SETUP_DISPLAY :
- « texte » (défaut) : console tty1, fonctionne sur toutes les TV ;
- « graphique » : pygame (kmsdrm) ; en cas d'échec au démarrage, retour au texte.

Le clavier est lu sur l'entrée standard (tty1, donnée par systemd : StandardInput=tty).
Code de sortie 0 = configuration terminée (l'écran normal reprend la main).
"""

from __future__ import annotations

import os
import select
import sys
import time

from berrycast import countries
from berrycast.setup import keyboards, wifi
from berrycast.setup.form import SetupForm
from berrycast.setup.keys import KeyDecoder
from berrycast.setup.session import Session

DONE_AUTO_EXIT = 20  # secondes avant de quitter tout seul l'écran « C'est prêt »


def build_session() -> Session:
    detected = wifi.detect_country()
    form = SetupForm(
        networks=wifi.scan(),
        countries=countries.sorted_countries(countries.country_names("fr"), first=detected),
        detected_country=detected,
        keyboard_index=keyboards.default_index(detected),
    )
    session = Session(form, scan=wifi.scan)
    session.keyboard_changed()  # disposition proposée appliquée tout de suite
    return session


class TextDisplay:
    def __init__(self, fd: int):
        from berrycast.setup import console_ui

        self.ui = console_ui
        self.fd = fd
        self.last = None

    def draw(self, session: Session) -> None:
        cols, rows = self.ui.terminal_size(self.fd)
        screen = self.ui.render(session, cols, rows)
        if screen != self.last:
            data = screen.encode("utf-8")
            while data:
                data = data[os.write(self.fd, data):]
            self.last = screen

    def invalidate(self) -> None:
        pass  # le texte est comparé à chaque fois : rien à faire

    def close(self) -> None:
        os.write(self.fd, b"\033[0m\033[2J\033[H")


class GraphicDisplay:
    def __init__(self):
        os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        import pygame

        from berrycast.setup.ui import SetupUI

        pygame.display.init()
        pygame.font.init()
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.mouse.set_visible(False)
        print(f"Affichage graphique {screen.get_size()}, pilote {pygame.display.get_driver()}",
              file=sys.stderr)
        self.pg = pygame
        self.screen = screen
        self.ui_class = SetupUI
        self.ui = None
        self.last_tick = None
        self.dirty = True

    def invalidate(self) -> None:
        self.dirty = True

    def draw(self, session: Session) -> None:
        if self.ui is None:
            self.ui = self.ui_class(self.pg, self.screen, session)
        self.pg.event.pump()
        # On ne redessine que si nécessaire : le Pi 3 dessine en logiciel.
        tick = (int(time.monotonic() * 2), session.state, session.busy, session.notice_visible())
        if self.dirty or tick != self.last_tick:
            self.ui.draw()
            self.last_tick, self.dirty = tick, False

    def close(self) -> None:
        self.pg.quit()


def make_display(fd: int):
    choice = os.environ.get("BERRYCAST_SETUP_DISPLAY", "texte")
    if choice == "graphique":
        try:
            return GraphicDisplay()
        except Exception as exc:  # pygame absent, pas d'écran DRM… -> texte
            print(f"Affichage graphique impossible ({exc}) : affichage texte", file=sys.stderr)
    return TextDisplay(sys.stdout.fileno())


def main() -> int:
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        print("Le clavier doit arriver par un terminal (StandardInput=tty).", file=sys.stderr)
        return 1

    import termios
    import tty

    saved = termios.tcgetattr(fd)
    tty.setraw(fd)  # chaque touche arrive tout de suite, sans écho
    display = None
    try:
        session = build_session()
        display = make_display(fd)
        decoder = KeyDecoder()
        done_since = None
        running = True
        while running:
            ready, _, _ = select.select([fd], [], [], 0.1)
            data = os.read(fd, 1024) if ready else b""
            for kind, value in decoder.feed(data, final=not ready):
                display.invalidate()
                running = session.handle(kind, value)
                if not running:
                    break
            if session.state == "done":
                done_since = done_since or time.monotonic()
                if time.monotonic() - done_since > DONE_AUTO_EXIT:
                    running = False
            display.draw(session)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        if display:
            display.close()
    ok = session.state == "done"
    print("Configuration terminée" if ok else "Configuration interrompue", file=sys.stderr)
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
