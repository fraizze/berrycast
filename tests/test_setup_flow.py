"""Tests du déroulé complet du premier lancement : session, application, démarrage auto,
affichage texte."""

import json
import re
import threading
import time

import pytest

from berrycast.setup import apply, autostart, console_ui
from berrycast.setup.form import SetupForm
from berrycast.setup.session import Session

NETWORKS = [{"ssid": "Ma Box", "signal": 80, "secure": True}]
COUNTRIES = [("CH", "Suisse"), ("FR", "France")]


def filled_session(submit_result):
    form = SetupForm(NETWORKS, COUNTRIES, detected_country="CH")
    form.rows_by_key["wifi_password"].value = "motdepasse"
    form.rows_by_key["pi_password"].value = "secret123"
    form.rows_by_key["pi_password2"].value = "secret123"
    sent = []

    def submit(req):
        sent.append(req)
        return submit_result

    session = Session(form, scan=lambda rescan: NETWORKS, submit=submit,
                      apply_keyboard=lambda layout: True)
    form.focus_key("submit")
    return session, sent


def test_session_success():
    session, sent = filled_session({"ok": True, "ip": "192.168.1.20"})
    assert session.handle("key", "enter") is True
    session.wait(2)
    assert session.state == "done"
    req = sent[0]
    assert req["ssid"] == "Ma Box" and req["psk"] == "motdepasse"
    assert req["country"] == "CH" and req["keyboard_layout"] == "ch"
    assert req["keyboard_variant"] == "fr" and req["pi_password"] == "secret123"
    assert session.handle("key", "enter") is False  # Entrée : terminer


def test_session_wrong_password_returns_to_form():
    session, _ = filled_session({"ok": False, "error": "wrong_password"})
    session.handle("key", "enter")
    session.wait(2)
    assert session.state == "form"
    assert "mot de passe" in session.error
    assert session.form.current.key == "wifi_password"


def test_session_ignores_keys_while_applying():
    gate = threading.Event()
    session, _ = filled_session({"ok": True})
    session.submit = lambda req: (gate.wait(2), {"ok": True})[1]
    session.handle("key", "enter")
    assert session.state == "applying"
    assert session.handle("key", "up") is True and session.form.current.key == "submit"
    gate.set()
    session.wait(2)
    assert session.state == "done"


def test_session_refresh_in_background():
    session, _ = filled_session({"ok": True})
    session.scan = lambda rescan: [{"ssid": "Nouveau", "signal": 99, "secure": False}] + NETWORKS
    session.form.focus_key("refresh")
    session.handle("key", "enter")
    session.wait(2)
    assert session.busy == ""
    assert "Nouveau" in [v for v, _ in session.form.rows_by_key["wifi"].options]


# --- Application (root) ------------------------------------------------------

VALID = {"keyboard_layout": "ch", "keyboard_variant": "fr", "device_name": "TV Salon",
         "ssid": "Ma Box", "psk": "motdepasse", "country": "CH", "pi_password": "secret123"}


def test_validate_request():
    assert apply.validate(VALID) == []
    bad = dict(VALID, device_name="", psk="court", pi_password="a:b", keyboard_layout="ch;rm",
               country="ZZ", ssid="")
    assert len(apply.validate(bad)) == 6
    assert apply.validate(dict(VALID, country=None, psk="")) == []  # international, ouvert


def test_update_keyboard_file():
    text = 'XKBMODEL="pc105"\nXKBLAYOUT="fr"\nXKBVARIANT=""\nXKBOPTIONS=""\n'
    out = apply.update_keyboard_file(text, "ch", "fr")
    assert 'XKBLAYOUT="ch"' in out and 'XKBVARIANT="fr"' in out and 'XKBMODEL="pc105"' in out
    assert apply.update_keyboard_file("", "us", "") == 'XKBLAYOUT="us"\nXKBVARIANT=""\n'


def test_explain_failure():
    assert apply.explain_failure(
        "Error: Connection activation failed: Secrets were required, but not provided"
    ) == "wrong_password"
    assert apply.explain_failure(
        "Error: Connection activation failed: The Wi-Fi network could not be found"
    ) == "not_found"
    assert apply.explain_failure("autre chose") == "failed"


def test_submit_roundtrip_with_fake_root(tmp_path):
    def fake_root():
        req_path = tmp_path / apply.REQUEST
        for _ in range(100):
            if req_path.exists():
                break
            time.sleep(0.02)
        req = json.loads(req_path.read_text(encoding="utf-8"))
        req_path.unlink()
        (tmp_path / apply.RESULT).write_text(json.dumps({"ok": True, "ip": req["ssid"]}))

    worker = threading.Thread(target=fake_root)
    worker.start()
    result = apply.submit({"ssid": "X"}, run_dir=tmp_path, timeout=5, poll=0.02)
    worker.join()
    assert result == {"ok": True, "ip": "X"}
    assert not (tmp_path / apply.REQUEST).exists()


def test_submit_timeout(tmp_path):
    assert apply.submit({}, run_dir=tmp_path, timeout=0.1, poll=0.02) == {
        "ok": False, "error": "timeout"}


# --- Démarrage automatique ---------------------------------------------------


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.mark.parametrize("profiles,expected_wait", [(0, 20), (1, 120)])
def test_autostart_waits_then_starts(profiles, expected_wait):
    clock = FakeClock()
    assert autostart.should_start(lambda: False, profiles, False, clock.sleep, clock) is True
    assert expected_wait <= clock.now <= expected_wait + 3


def test_autostart_skipped_when_wifi_connects():
    clock = FakeClock()
    assert autostart.should_start(lambda: clock.now > 10, 1, False, clock.sleep, clock) is False
    assert clock.now < 20


def test_autostart_forced():
    assert autostart.should_start(lambda: True, 1, True) is True


# --- Affichage texte ---------------------------------------------------------


def visible_lines(screen: str, rows: int) -> list[str]:
    """Reconstitue l'écran (texte seul) à partir des positions « Échap [ ligne ; col H »."""
    grid = [""] * rows
    for row, col, text in re.findall(r"\x1b\[(\d+);(\d+)H((?:(?!\x1b\[\d+;\d+H).)*)", screen):
        plain = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", text)
        r, c = int(row) - 1, int(col) - 1
        line = grid[r].ljust(c)
        grid[r] = line[:c] + plain + line[c + len(plain):]
    return grid


@pytest.mark.parametrize("cols,rows", [(120, 33), (80, 22)])
def test_console_form_fits_screen(cols, rows):
    session, _ = filled_session({"ok": True})
    form = session.form
    form.focus = 0
    lines = visible_lines(console_ui.render(session, cols, rows), rows)
    text = "\n".join(lines)
    assert "Bienvenue sur BerryCast" in text
    assert "Suisse romand" in text and "Ma Box" in text and "Valider" in text
    assert "••••••••••" in text  # mot de passe masqué
    assert all(len(line) <= cols for line in lines)


def test_console_dropdown_and_states():
    session, _ = filled_session({"ok": True, "ip": "192.168.1.20"})
    form = session.form
    form.focus_key("country")
    form.handle("key", "enter")
    text = "\n".join(visible_lines(console_ui.render(session, 120, 33), 33))
    assert "┌" in text and "France" in text

    form.dropdown = None
    session.state = "applying"
    text = "\n".join(visible_lines(console_ui.render(session, 120, 33), 33))
    assert "Connexion au Wi-Fi « Ma Box »" in text

    session.state, session.result = "done", {"ok": True, "ip": "192.168.1.20"}
    text = "\n".join(visible_lines(console_ui.render(session, 120, 33), 33))
    assert "C'est prêt" in text and "192.168.1.20" in text


def test_console_shows_connection_error():
    session, _ = filled_session({"ok": False, "error": "not_found"})
    session.handle("key", "enter")
    session.wait(2)
    text = "\n".join(visible_lines(console_ui.render(session, 120, 33), 33))
    assert "introuvable" in text
