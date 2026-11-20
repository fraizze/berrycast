"""Tests de devsetup.apply_file, avec les commandes système remplacées par des faux."""

import pytest

from berrycast.dev import devsetup, wifi_file


@pytest.fixture
def fake_system(monkeypatch):
    """Remplace toutes les actions système et note ce qui a été demandé."""
    calls = []
    monkeypatch.setattr(devsetup, "apply_country", lambda c: calls.append(("country", c)))
    monkeypatch.setattr(devsetup, "apply_ssh_password", lambda p: calls.append(("ssh", p)))
    monkeypatch.setattr(devsetup, "enable_wifi_radio", lambda: None)
    monkeypatch.setattr(devsetup, "wait_for_wifi_device", lambda: True)
    monkeypatch.setattr(devsetup, "visible_ssids", lambda: ["iPhone d’Alex"])
    monkeypatch.setattr(devsetup, "configured_ssid", lambda: None)

    def fake_wifi(ssid, psk):
        calls.append(("wifi", ssid, psk))
        return f"Wi-Fi « {ssid} » : connecté"

    monkeypatch.setattr(devsetup, "apply_wifi", fake_wifi)
    return calls


def write(tmp_path, text):
    path = tmp_path / wifi_file.FILE_NAME
    path.write_text(text, encoding="utf-8")
    return path


def test_apply_full_file_and_erase_secrets(tmp_path, fake_system):
    path = write(
        tmp_path,
        "wifi_nom=iPhone d'Alex\nwifi_mot_de_passe=motdepasse\n"
        "pays=FR\nssh_mot_de_passe=secret123\n",
    )
    messages, errors = devsetup.apply_file(path)

    assert errors == []
    assert ("country", "FR") in fake_system
    assert ("ssh", "secret123") in fake_system
    assert ("wifi", "iPhone d’Alex", "motdepasse") in fake_system  # apostrophe corrigée

    rewritten = path.read_text(encoding="utf-8")
    assert "motdepasse" not in rewritten
    assert "secret123" not in rewritten
    assert wifi_file.parse(rewritten)["wifi_nom"] == "iPhone d'Alex"
    assert "Lu par le Raspberry Pi" in rewritten


def test_empty_template_is_left_untouched(tmp_path, fake_system):
    original = wifi_file.render(country="FR")
    path = tmp_path / wifi_file.FILE_NAME
    path.write_bytes(original.encode("utf-8"))

    assert devsetup.apply_file(path) == ([], [])
    assert fake_system == []
    assert path.read_bytes() == original.encode("utf-8")


def test_already_applied_open_network_is_not_reapplied(tmp_path, fake_system, monkeypatch):
    monkeypatch.setattr(devsetup, "configured_ssid", lambda: "Gare")
    path = write(tmp_path, "wifi_nom=Gare\npays=FR\n")
    assert devsetup.apply_file(path) == ([], [])
    assert fake_system == []


def test_errors_are_reported_in_file_and_secrets_erased(tmp_path, fake_system):
    path = write(tmp_path, "wifi_nom=Box\nwifi_mot_de_passe=court\nssh_mot_de_passe=abc\n")
    messages, errors = devsetup.apply_file(path)

    assert len(errors) == 2
    assert not any(c[0] in ("wifi", "ssh") for c in fake_system)
    rewritten = path.read_text(encoding="utf-8")
    assert "court" not in rewritten.split("ERREUR")[0]  # la valeur n'est pas recopiée
    assert "wifi_mot_de_passe=\n" in rewritten  # read_text convertit CRLF en \n
    assert "ERREUR" in rewritten
