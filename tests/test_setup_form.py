"""Tests du premier lancement au clavier : formulaire, touches, Wi-Fi, pays, claviers."""

import json

import pytest

from berrycast import countries
from berrycast.setup import keyboards, wifi
from berrycast.setup.form import APPLY_KEYBOARD, MANUAL, QUIT, REFRESH, SUBMITTED, SetupForm
from berrycast.setup.keys import KeyDecoder

NETWORKS = [
    {"ssid": "Ma Box", "signal": 80, "secure": True},
    {"ssid": "Gare", "signal": 40, "secure": False},
]
COUNTRIES = [("CH", "Suisse"), ("DE", "Allemagne"), ("FR", "France")]


def make_form(**kw):
    return SetupForm(NETWORKS, COUNTRIES, **kw)


def keys(form, *events):
    """Envoie une suite de touches : "down", "enter"… ou du texte entre guillemets « 'abc' »."""
    actions = []
    for ev in events:
        if ev.startswith("'"):
            for ch in ev.strip("'"):
                actions.append(form.handle("char", ch))
        else:
            actions.append(form.handle("key", ev))
    return actions


def goto(form, key):
    form.focus = [r.key for r in form.rows].index(key)


# --- Formulaire ----------------------------------------------------------------


def test_rows_for_secure_network():
    form = make_form()
    assert [r.key for r in form.rows] == [
        "keyboard", "name", "wifi", "refresh", "wifi_password", "country",
        "pi_password", "pi_password2", "submit",
    ]
    assert form.rows_by_key["wifi"].value == "Ma Box"  # meilleur signal présélectionné


def test_open_network_hides_password_and_manual_shows_name():
    form = make_form()
    goto(form, "wifi")
    keys(form, "right")
    assert form.rows_by_key["wifi"].value == "Gare"
    assert "wifi_password" not in [r.key for r in form.rows]
    keys(form, "right")
    assert form.rows_by_key["wifi"].value == MANUAL
    assert "wifi_manual" in [r.key for r in form.rows]


def test_keyboard_change_asks_to_apply():
    form = make_form()
    assert keys(form, "right") == [APPLY_KEYBOARD]
    assert form.rows_by_key["keyboard"].value == "1"


def test_typing_and_backspace():
    form = make_form(device_name="")
    goto(form, "name")
    keys(form, "'TV Salon!'", "backspace")
    assert form.rows_by_key["name"].value == "TV Salon"


def test_dropdown_navigation_and_letter_jump():
    form = make_form()
    goto(form, "country")
    keys(form, "enter")
    assert form.dropdown is not None
    keys(form, "'f'")  # saute à « France »
    keys(form, "enter")
    assert form.dropdown is None
    assert form.rows_by_key["country"].value == "FR"
    keys(form, "enter", "esc")  # Échap ferme sans changer
    assert form.rows_by_key["country"].value == "FR"


def test_letter_on_choice_opens_dropdown_and_jumps():
    form = make_form()
    goto(form, "country")
    keys(form, "'a'")
    assert form.dropdown.index == 1  # Allemagne


def test_refresh_and_quit_actions():
    form = make_form()
    goto(form, "refresh")
    assert keys(form, "enter") == [REFRESH]
    assert keys(form, "f5") == [REFRESH]
    assert keys(form, "ctrl-c") == [QUIT]


def fill_valid(form):
    goto(form, "wifi_password")
    keys(form, "'motdepasse'")
    goto(form, "pi_password")
    keys(form, "'secret123'", "down", "'secret123'")


def test_submit_valid_form():
    form = make_form(detected_country="CH")
    fill_valid(form)
    goto(form, "submit")
    assert keys(form, "enter") == [SUBMITTED]
    res = form.result()
    assert res["ssid"] == "Ma Box" and res["psk"] == "motdepasse"
    assert res["country"] == "CH" and res["pi_password"] == "secret123"
    assert res["device_name"] == "BerryCast"
    assert res["keyboard"] == keyboards.LAYOUTS[0]


def test_submit_errors_focus_first_problem():
    form = make_form()
    goto(form, "pi_password")
    keys(form, "'court'")
    goto(form, "submit")
    assert keys(form, "enter") == [None]
    assert form.rows_by_key["wifi_password"].error
    assert form.rows_by_key["pi_password"].error
    assert form.current.key == "wifi_password"


def test_password_confirmation_mismatch():
    form = make_form()
    goto(form, "wifi_password")
    keys(form, "'motdepasse'")
    goto(form, "pi_password")
    keys(form, "'secret123'", "down", "'secret124'")
    assert not form.validate()
    assert form.rows_by_key["pi_password2"].error


def test_empty_country_is_allowed_international():
    form = make_form()
    fill_valid(form)
    assert form.validate()
    assert form.result()["country"] is None


def test_manual_network_open_or_with_password():
    form = make_form()
    goto(form, "wifi")
    keys(form, "left")  # dernière option : saisie manuelle
    assert form.rows_by_key["wifi"].value == MANUAL
    goto(form, "wifi_manual")
    keys(form, "'Cache'")
    goto(form, "pi_password")
    keys(form, "'secret123'", "down", "'secret123'")
    assert form.validate()
    assert form.result()["ssid"] == "Cache" and form.result()["psk"] == ""


def test_refreshed_list_keeps_choice():
    form = make_form()
    goto(form, "wifi")
    keys(form, "right")  # Gare
    form.set_networks([{"ssid": "Nouveau", "signal": 90, "secure": True}] + NETWORKS)
    assert form.rows_by_key["wifi"].value == "Gare"


def test_no_networks_defaults_to_manual():
    form = SetupForm([], COUNTRIES)
    assert form.rows_by_key["wifi"].value == MANUAL


# --- Touches -----------------------------------------------------------------


def test_key_decoder():
    d = KeyDecoder()
    assert d.feed(b"\x1b[A\x1b[B\r\x7fa\xc3\xa9") == [
        ("key", "up"), ("key", "down"), ("key", "enter"), ("key", "backspace"),
        ("char", "a"), ("char", "é"),
    ]


def test_key_decoder_split_sequences_and_lone_escape():
    d = KeyDecoder()
    assert d.feed(b"\x1b") == []  # peut-être le début d'une séquence
    assert d.feed(b"[5~") == [("key", "pgup")]
    assert d.feed(b"\x1b") == []
    assert d.feed(b"", final=True) == [("key", "esc")]
    assert d.feed(b"\xc3") == []  # moitié d'un « é »
    assert d.feed(b"\xa9") == [("char", "é")]
    assert d.feed(b"\x1b[99Zx") == [("char", "x")]  # séquence inconnue ignorée


# --- Wi-Fi et pays -----------------------------------------------------------


def test_parse_scan():
    out = "Box\\:Salon:70:WPA2\nBox\\:Salon:30:WPA2\n:90:WPA2\nGare:55:\nCafé:20:--\n"
    nets = wifi.parse_scan(out)
    assert [n["ssid"] for n in nets] == ["Box:Salon", "Gare", "Café"]
    assert nets[0]["secure"] and not nets[1]["secure"] and not nets[2]["secure"]


def test_detect_country_from_beacons():
    out = "BSS aa\n\tCountry: CH\tEnvironment: Indoor/Outdoor\nBSS bb\n\tCountry: CH\n" \
          "BSS cc\n\tCountry: FR\n\tCountry: XX\n"
    assert wifi.parse_scan_countries(out) == "CH"
    assert wifi.parse_scan_countries("rien") is None


def test_country_names_from_iso_codes(tmp_path):
    data = {"3166-1": [{"alpha_2": "CH", "name": "Switzerland"},
                       {"alpha_2": "EG", "name": "Egypt"}]}
    path = tmp_path / "iso.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    names = countries.country_names("fr", json_path=str(path), locale_dir=str(tmp_path))
    assert names["CH"] == "Switzerland"  # pas de traduction disponible ici : nom anglais
    assert names["FR"] == "FR"  # absent du fichier : le code
    assert len(names) == 249


def test_country_names_without_package():
    names = countries.country_names(json_path="/inexistant.json")
    assert names["CH"] == "CH"


def test_sorted_countries_detected_first_and_accents():
    names = {"CH": "Suisse", "EG": "Égypte", "ES": "Espagne", "AF": "Afghanistan"}
    assert [c for c, _ in countries.sorted_countries(names)] == ["AF", "EG", "ES", "CH"]
    assert countries.sorted_countries(names, first="CH")[0] == ("CH", "Suisse")


@pytest.mark.parametrize("country,label", [
    ("CH", "Suisse romand (QWERTZ)"),
    ("FR", "Français (AZERTY)"),
    (None, "Français (AZERTY)"),
])
def test_default_keyboard(country, label):
    assert keyboards.LAYOUTS[keyboards.default_index(country)].label == label
