"""Tests de l'écran de développement et de la lecture de nmcli."""

from berrycast.dev import screen
from berrycast.dev.nm import split_terse
from berrycast.dev.screen import Info, layout, render_lines


def test_write_all_handles_partial_writes(monkeypatch):
    chunks = []

    def short_write(fd, data):
        piece = bytes(data[:3])  # le terminal n'accepte que 3 octets à la fois
        chunks.append(piece)
        return len(piece)

    monkeypatch.setattr(screen.os, "write", short_write)
    screen.write_all(1, "écran OK".encode())
    assert b"".join(chunks) == "écran OK".encode()


def test_output_is_stdout_by_default(monkeypatch):
    monkeypatch.setattr(screen, "TTY", None)
    monkeypatch.setattr(screen.sys.stdout, "fileno", lambda: 1)
    assert screen.open_output() == 1


def test_split_terse_with_escapes():
    fields = split_terse(r"wlan0:wifi:connected:Box\:Salon")
    assert fields == ["wlan0", "wifi", "connected", "Box:Salon"]
    assert split_terse(r"a\\b:c") == ["a\\b", "c"]
    assert split_terse("seul") == ["seul"]
    assert split_terse("") == [""]


def test_render_connected():
    info = Info(
        hostname="berrycast",
        wifi_state="connected",
        ssid="MonIphone",
        signal=72,
        addresses={"wlan0": "172.20.10.3"},
        ssh_password_set=True,
        build="abc1234 du 2026-11-20",
    )
    lines = render_lines(info)
    assert lines[0] == "BerryCast dev"
    assert "Wi-Fi : connecté à « MonIphone » (72 %)" in lines
    assert "Adresse IP (Wi-Fi) : 172.20.10.3" in lines
    assert "SSH : ssh pi@berrycast.local" in lines
    assert "  ou  ssh pi@172.20.10.3" in lines
    assert not any("ATTENTION" in line for line in lines)
    assert lines[-1] == "version abc1234 du 2026-11-20"


def test_render_not_configured():
    info = Info(wifi_state="unavailable", ssh_password_set=False, errors=["pays invalide"])
    lines = render_lines(info)
    assert "Wi-Fi : indisponible (pays non réglé ?)" in lines
    assert "Adresse IP : aucune" in lines
    assert any("clavier" in line for line in lines)
    assert any(line.startswith("ATTENTION") for line in lines)
    assert "ERREUR : pays invalide" in lines


def test_render_world_regdomain_warning():
    lines = render_lines(Info(wifi_state="connected", ssid="Box", regdomain="00"))
    assert "ATTENTION : pays Wi-Fi non défini, réglage international utilisé" in lines


def test_render_country_shown_without_warning():
    lines = render_lines(Info(wifi_state="connected", ssid="Box", regdomain="CH"))
    assert "Pays Wi-Fi : CH" in lines
    assert not any("ATTENTION" in line for line in lines)


def test_layout_centers_and_fits():
    out = layout(["Titre", "abc"], cols=11, rows=6)
    assert out.count("\n") == 2 + 1  # 2 lignes vides au-dessus + 1 entre les deux lignes
    assert "    abc" in out
    # Une ligne trop longue est coupée à la largeur de l'écran
    assert "x" * 12 not in layout(["T", "x" * 50], cols=11, rows=6)
