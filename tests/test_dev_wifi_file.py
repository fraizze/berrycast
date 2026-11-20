"""Tests du fichier berrycast-wifi.txt (image de développement)."""

from berrycast.dev import wifi_file
from berrycast.dev.wifi_file import parse, pick_ssid, render, validate


def test_parse_notepad_file_with_bom_and_crlf():
    text = "﻿# commentaire\r\nwifi_nom = Mon iPhone \r\nwifi_mot_de_passe=abc=def123\r\npays=fr\r\n"
    assert parse(text) == {
        "wifi_nom": "Mon iPhone",
        "wifi_mot_de_passe": "abc=def123",  # seul le premier « = » sépare
        "pays": "fr",
    }


def test_parse_ignores_unknown_keys_and_garbage():
    assert parse("bonjour\nfoo=bar\nWIFI_NOM=X\n") == {"wifi_nom": "X"}


def test_validate_full_settings():
    s = validate(parse(
        "wifi_nom=MonIphone\nwifi_mot_de_passe=motdepasse\npays=fr\nssh_mot_de_passe=secret123\n"
    ))
    assert s.errors == []
    assert (s.ssid, s.psk, s.country, s.ssh_password) == (
        "MonIphone", "motdepasse", "FR", "secret123"
    )
    assert s.has_secrets()


def test_validate_empty_template_does_nothing():
    s = validate(parse(render(country="FR")))
    assert s.errors == []
    assert s.ssid is None and s.ssh_password is None
    assert s.country == "FR"
    assert not s.has_secrets()


def test_open_network_without_password():
    s = validate({"wifi_nom": "Gare"})
    assert s.ssid == "Gare" and s.psk is None and s.errors == []


def test_validate_errors():
    s = validate({
        "pays": "France",
        "wifi_nom": "Box",
        "wifi_mot_de_passe": "court",
        "ssh_mot_de_passe": "1234",
    })
    assert len(s.errors) == 3
    assert s.country is None and s.ssid is None and s.ssh_password is None


def test_psk_rules():
    assert validate({"wifi_nom": "X", "wifi_mot_de_passe": "a" * 63}).ssid == "X"
    assert validate({"wifi_nom": "X", "wifi_mot_de_passe": "z" * 64}).errors  # 64 non hex
    assert validate({"wifi_nom": "X", "wifi_mot_de_passe": "ab" * 32}).errors == []  # 64 hex
    assert validate({"wifi_nom": "X", "wifi_mot_de_passe": "mötdepasse"}).errors  # non ASCII


def test_ssh_password_with_colon_refused():
    assert validate({"ssh_mot_de_passe": "abc:defgh"}).errors


def test_password_without_ssid():
    assert validate({"wifi_mot_de_passe": "motdepasse"}).errors


def test_ssid_too_long():
    assert validate({"wifi_nom": "é" * 17}).errors  # 34 octets


def test_pick_ssid_exact_match():
    assert pick_ssid("Box", ["Box", "box"]) == "Box"


def test_pick_ssid_curly_apostrophe_from_iphone():
    visible = ["Freebox-1234", "iPhone d’Alex"]
    assert pick_ssid("iPhone d'Alex", visible) == "iPhone d’Alex"


def test_pick_ssid_keeps_typed_name_when_not_visible_or_ambiguous():
    assert pick_ssid("Absent", ["Autre"]) == "Absent"
    assert pick_ssid("box", ["Box", "BOX"]) == "box"


def test_render_has_no_secrets_and_crlf():
    text = render(ssid="MonIphone", country="FR", messages=["Lu le 01/01/2026", "ERREUR : x"])
    values = parse(text)
    assert values == {
        "wifi_nom": "MonIphone",
        "wifi_mot_de_passe": "",
        "pays": "FR",
        "ssh_mot_de_passe": "",
    }
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")
    assert "# >>> ERREUR : x" in text


def test_render_with_braces_in_ssid():
    assert parse(render(ssid="Wi{fi}"))["wifi_nom"] == "Wi{fi}"


def test_file_name():
    assert wifi_file.FILE_NAME == "berrycast-wifi.txt"
