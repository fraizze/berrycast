"""Tests de l'étape A du mode configuration (point d'accès, QR, portail, écran)."""

import json
import struct
import urllib.request

import pytest

from berrycast.dev.screen import render_setup, setup_text
from berrycast.display import fontpatch
from berrycast.setup import hotspot, qr
from berrycast.setup.portal import CodeGuard, Portal, format_code, is_captive_check

# --- Police console -------------------------------------------------------


def make_psf2(chars_per_glyph, width=16, height=32):
    count = len(chars_per_glyph)
    charsize = (width + 7) // 8 * height
    header = struct.pack("<IIIIIIII", fontpatch.PSF2_MAGIC, 0, 32, 1, count, charsize,
                         height, width)
    glyphs = bytes([0x55]) * (count * charsize)
    table = b"".join("".join(chars).encode() + b"\xff" for chars in chars_per_glyph)
    return header + glyphs + table


def test_fontpatch_adds_upper_half_block():
    font = make_psf2([["A"], ["░"], ["█"]])
    patched = fontpatch.add_upper_half_block(font)
    count, charsize = struct.unpack("<II", patched[16:24])
    glyph = patched[32 + charsize:32 + 2 * charsize]
    assert glyph[:32] == b"\xff" * 32  # 16 premières rangées pleines (2 octets chacune)
    assert glyph[32:] == b"\x00" * 32  # 16 dernières vides
    table = fontpatch._parse_unicode_table(patched[32 + count * charsize:], count)
    assert table == [["A"], ["▀"], ["█"]]
    assert fontpatch.add_upper_half_block(patched) == patched  # idempotent


def test_fontpatch_errors():
    with pytest.raises(fontpatch.FontError):
        fontpatch.add_upper_half_block(b"\x00" * 40)
    with pytest.raises(fontpatch.FontError):
        fontpatch.add_upper_half_block(make_psf2([["A"], ["B"]]))


# --- QR code ----------------------------------------------------------------


def test_wifi_payload_escaping():
    assert qr.wifi_payload("BerryCast-Setup-AB12", "k7m2p9xq") == (
        "WIFI:T:WPA;S:BerryCast-Setup-AB12;P:k7m2p9xq;;"
    )
    assert qr.wifi_payload('a;b,c:d"e\\', "p;w") == 'WIFI:T:WPA;S:a\\;b\\,c\\:d\\"e\\\\;P:p\\;w;;'
    assert qr.wifi_payload("Gare", None) == "WIFI:T:nopass;S:Gare;;"


def test_terminal_lines_shape():
    matrix = [[True, False, True], [False, True, False], [True, True, True]]
    lines = qr.to_terminal_lines(matrix, quiet=2)
    assert len(lines) == 4  # 3 + 2*2 = 7 rangées -> 8 avec complément -> 4 lignes
    for line in lines:
        assert line.count(qr.UPPER_HALF_BLOCK) == qr.visible_width(matrix, quiet=2) == 7
        assert line.endswith("\033[0m")


def test_real_qr_matrix_if_library_available():
    pytest.importorskip("qrcode")
    matrix = qr.qr_matrix(qr.wifi_payload("BerryCast-Setup-AB12", "k7m2p9xq"))
    assert len(matrix) <= 29  # version 3 au plus : tient à côté du texte en 720p
    assert len(qr.to_terminal_lines(matrix)) <= 17
    assert qr.visible_width(matrix) <= 33


# --- Point d'accès ---------------------------------------------------------


def test_setup_ssid_and_password():
    assert hotspot.setup_ssid("b8:27:eb:12:ab:cd") == "BerryCast-Setup-ABCD"
    pw = hotspot.random_password()
    assert len(pw) == 8 and set(pw) <= set(hotspot.PASSWORD_ALPHABET)


def test_ap_args_for_pi3_and_iphone():
    args = hotspot.ap_connection_args("BerryCast-Setup-ABCD", "k7m2p9xq")
    pairs = dict(zip(args[3::2], args[4::2], strict=False))
    assert pairs["802-11-wireless.mode"] == "ap"
    assert pairs["wifi-sec.pmf"] == "disable"
    assert pairs["wifi-sec.proto"] == "rsn"
    assert pairs["ipv4.method"] == "shared"
    assert pairs["connection.autoconnect"] == "no"
    assert args[-1] == "k7m2p9xq"


def test_parse_scan():
    out = "\n".join([
        "Box\\:Salon:70:WPA2:6",
        "Box\\:Salon:40:WPA2:1",
        ":90:WPA2:11",  # réseau caché
        "BerryCast-Setup-ABCD:99:WPA2:6",  # notre propre point d'accès
        "Gare:55::1",
    ])
    nets = hotspot.parse_scan(out)
    assert [n["ssid"] for n in nets] == ["Box:Salon", "Gare"]
    assert nets[0]["signal"] == 70 and nets[0]["secure"] is True
    assert nets[1]["secure"] is False


# --- Portail ----------------------------------------------------------------


def test_code_guard_attempts_and_lock():
    now = [100.0]
    guard = CodeGuard("123456", max_attempts=3, lock_seconds=60, clock=lambda: now[0])
    assert guard.verify("000000") == {"ok": False, "remaining": 2}
    assert guard.verify("111111")["remaining"] == 1
    locked = guard.verify("222222")
    assert locked["locked_seconds"] == 60
    assert guard.verify("123456")["ok"] is False  # bloqué, même avec le bon code
    now[0] += 61
    ok = guard.verify("123 456")  # espaces tolérés
    assert ok["ok"] is True and guard.is_valid_token(ok["token"])
    assert not guard.is_valid_token("faux")


def test_captive_detection():
    assert is_captive_check("captive.apple.com", "10.42.0.1")
    assert is_captive_check("connectivitycheck.gstatic.com:80", "10.42.0.1")
    assert not is_captive_check("10.42.0.1", "10.42.0.1")
    assert not is_captive_check("10.42.0.1:80", "10.42.0.1")
    assert format_code("123456") == "123 456"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def test_portal_http():
    portal = Portal(CodeGuard("654321"), "127.0.0.1", port=0, context=lambda: {"ssid": "X"})
    port = portal.server.server_address[1]
    portal.start()
    base = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(NoRedirect)
    try:
        page = opener.open(f"{base}/").read().decode()
        assert "Code affiché sur la TV" in page

        req = urllib.request.Request(f"{base}/hotspot-detect.html",
                                     headers={"Host": "captive.apple.com"})
        with pytest.raises(urllib.error.HTTPError) as exc:
            opener.open(req)
        assert exc.value.code == 302
        assert exc.value.headers["Location"] == "http://127.0.0.1/"

        info = json.loads(opener.open(f"{base}/api/info").read())
        assert info == {"ssid": "X", "locked_seconds": 0}

        def verify(code):
            req = urllib.request.Request(f"{base}/api/verify", method="POST",
                                         data=json.dumps({"code": code}).encode(),
                                         headers={"Content-Type": "application/json"})
            return json.loads(opener.open(req).read())

        assert verify("000000")["ok"] is False
        assert verify("654321")["ok"] is True
    finally:
        portal.stop()


# --- Écran de configuration -------------------------------------------------

SETUP = {"active": True, "ssid": "BerryCast-Setup-ABCD", "password": "k7m2p9xq",
         "url": "http://10.42.0.1", "code": "123456"}


def test_setup_text_contents():
    text = "\n".join(setup_text(SETUP))
    for expected in ("Bienvenue", "BerryCast-Setup-ABCD", "k7m2p9xq", "http://10.42.0.1",
                     "123 456"):
        assert expected in text


QR_LINE = "#" * 33


def test_render_setup_side_by_side_on_1080p():
    out = render_setup(SETUP, cols=120, rows=33, qr_lines=[QR_LINE] * 17, qr_width=33)
    assert out.count(QR_LINE) == 17
    assert "123 456" in out


def test_render_setup_fits_720p():
    # 1280x720 avec une police 16x32 : 80 colonnes, 22 lignes
    out = render_setup(SETUP, cols=80, rows=22, qr_lines=[QR_LINE] * 17, qr_width=33)
    assert out.count(QR_LINE) == 17


def test_render_setup_without_room_for_qr():
    out = render_setup(SETUP, cols=60, rows=16, qr_lines=[QR_LINE] * 17, qr_width=33)
    assert "#" not in out  # pas de QR, mais le texte est là
    assert "123 456" in out
