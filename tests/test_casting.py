"""Tests Miracast / AirPlay sans Raspberry Pi : messages WFD, négociation RTSP complète
(contre une fausse source Windows), lecteur, UxPlay, état des diffusions, écran."""

import socket
import threading

import pytest

from berrycast import audio, cast_state
from berrycast.airplay import service as airplay
from berrycast.dev.screen import Info, is_casting, pin_lines, pin_request, render_lines
from berrycast.display import bigdigits
from berrycast.miracast import pipeline, wfd
from berrycast.miracast.rtsp_sink import RtspSink
from berrycast.miracast.service import parse_ipv4

# --- WFD -------------------------------------------------------------------------


def test_wfd_ies_are_valid_subelements():
    data, pos, ids = wfd.WFD_IES, 0, []
    while pos < len(data):
        ids.append(data[pos])
        length = int.from_bytes(data[pos + 1:pos + 3], "big")
        pos += 3 + length
    assert pos == len(data) and ids == [0, 1, 6]
    assert wfd.WFD_IES[3:9].hex() == "00111c44012c"  # sink principal, port 7236


def test_wps_pin_checksum():
    assert wfd.wps_checksum(1234567) == 0  # 12345670 : exemple de la norme WPS
    for _ in range(50):
        pin = wfd.new_pin()
        assert len(pin) == 8 and pin.isdigit()
        assert wfd.wps_checksum(int(pin[:7])) == int(pin[7])
    assert wfd.format_pin("12345670") == "1234 5670"


def test_rtsp_parser_handles_split_and_merged_messages():
    m1 = b"OPTIONS * RTSP/1.0\r\nCSeq: 1\r\nRequire: org.wfa.wfd1.0\r\n\r\n"
    body = b"wfd_video_formats\r\nwfd_audio_codecs\r\n"
    m3 = (b"GET_PARAMETER rtsp://localhost/wfd1.0 RTSP/1.0\r\nCSeq: 2\r\n"
          b"Content-Type: text/parameters\r\nContent-Length: " + str(len(body)).encode()
          + b"\r\n\r\n" + body)
    parser = wfd.RtspParser()
    data = m1 + m3
    msgs = parser.feed(data[:30]) + parser.feed(data[30:70]) + parser.feed(data[70:])
    assert [m.method for m in msgs] == ["OPTIONS", "GET_PARAMETER"]
    assert msgs[1].cseq == "2"
    assert msgs[1].parameters() == ["wfd_video_formats", "wfd_audio_codecs"]


def test_answer_get_parameter_only_known():
    body = wfd.answer_get_parameter(
        ["wfd_audio_codecs", "wfd_display_edid", "wfd_client_rtp_ports"], "TV Salon")
    assert body == ("wfd_audio_codecs: AAC 00000001 00\r\n"
                    "wfd_client_rtp_ports: RTP/AVP/UDP;unicast 1028 0 mode=play\r\n")


def test_transport_and_session_helpers():
    assert wfd.server_port("RTP/AVP/UDP;unicast;client_port=1028;server_port=5000-5001") == "5000"
    assert wfd.session_id("6B8B4567;timeout=30") == "6B8B4567"


# --- Négociation RTSP complète contre une fausse source Windows ----------------------


class FakeWindowsSource:
    """Joue le rôle du PC Windows : envoie M1, M3, M4, M5 et répond à M2, M6, M7."""

    def __init__(self, sock):
        self.sock = sock
        self.parser = wfd.RtspParser()
        self.received = []

    def recv_one(self):
        while True:
            msgs = self.parser.feed(b"")
            if msgs:
                return msgs[0]
            data = self.sock.recv(4096)
            if not data:
                return None
            msgs = self.parser.feed(data)
            if msgs:
                # garde les messages en trop pour l'appel suivant
                self.parser.buffer = b"".join(
                    wfd.build(m.first_line, {**m.headers}, m.body) for m in msgs[1:]
                ) + self.parser.buffer
                self.received.append(msgs[0])
                return msgs[0]

    def send(self, data: bytes):
        self.sock.sendall(data)

    def run(self):
        s = self.send
        s(wfd.build("OPTIONS * RTSP/1.0", {"CSeq": "1", "Require": "org.wfa.wfd1.0"}))
        assert self.recv_one().status == 200  # réponse à M1
        m2 = self.recv_one()
        assert m2.method == "OPTIONS"
        s(wfd.response(m2.cseq, {"Public": "org.wfa.wfd1.0, SETUP, TEARDOWN, PLAY, PAUSE, "
                                           "GET_PARAMETER, SET_PARAMETER"}))
        s(wfd.build("GET_PARAMETER rtsp://localhost/wfd1.0 RTSP/1.0", {"CSeq": "2"},
                    "wfd_video_formats\r\nwfd_audio_codecs\r\nwfd_client_rtp_ports\r\n"
                    "intel_friendly_name\r\n"))
        m3r = self.recv_one()
        assert "wfd_client_rtp_ports: RTP/AVP/UDP;unicast 1028" in m3r.body
        assert "intel_friendly_name: TV Salon" in m3r.body
        s(wfd.build("SET_PARAMETER rtsp://localhost/wfd1.0 RTSP/1.0", {"CSeq": "3"},
                    "wfd_video_formats: 00 00 02 10 00000080 00000000 00000000 00 0000 0000 "
                    "00 none none\r\nwfd_audio_codecs: AAC 00000001 00\r\n"
                    "wfd_presentation_URL: rtsp://192.168.173.80/wfd1.0/streamid=0 none\r\n"
                    "wfd_client_rtp_ports: RTP/AVP/UDP;unicast 1028 0 mode=play\r\n"))
        assert self.recv_one().status == 200
        s(wfd.build("SET_PARAMETER rtsp://localhost/wfd1.0 RTSP/1.0", {"CSeq": "4"},
                    "wfd_trigger_method: SETUP\r\n"))
        assert self.recv_one().status == 200
        m6 = self.recv_one()
        assert m6.method == "SETUP"
        assert m6.first_line.startswith("SETUP rtsp://192.168.173.80/wfd1.0/streamid=0")
        assert "client_port=1028" in m6.headers["transport"]
        s(wfd.response(m6.cseq, {"Session": "6B8B4567;timeout=30",
                                 "Transport": "RTP/AVP/UDP;unicast;client_port=1028;"
                                              "server_port=5000"}))
        m7 = self.recv_one()
        assert m7.method == "PLAY" and m7.headers["session"] == "6B8B4567"
        s(wfd.response(m7.cseq))
        idr = self.recv_one()
        assert idr.method == "SET_PARAMETER" and "wfd_idr_request" in idr.body
        s(wfd.response(idr.cseq))
        # M16 : maintien de la session
        s(wfd.build("GET_PARAMETER rtsp://localhost/wfd1.0 RTSP/1.0", {"CSeq": "5"}))
        keepalive = self.recv_one()
        assert keepalive.status == 200 and keepalive.cseq == "5"
        # Fin demandée par Windows
        s(wfd.build("SET_PARAMETER rtsp://localhost/wfd1.0 RTSP/1.0", {"CSeq": "6"},
                    "wfd_trigger_method: TEARDOWN\r\n"))
        assert self.recv_one().status == 200
        teardown = self.recv_one()
        assert teardown.method == "TEARDOWN"
        self.sock.close()


def test_full_negotiation_with_fake_windows():
    sink_sock, source_sock = socket.socketpair()
    events = []
    sink = RtspSink(sink_sock, "192.168.173.80", "TV Salon",
                    on_play=lambda: events.append("play"), on_stop=lambda: events.append("stop"))
    source = FakeWindowsSource(source_sock)
    errors = []

    def run_source():
        try:
            source.run()
        except Exception as exc:  # remonte l'erreur au test
            errors.append(exc)
            source_sock.close()

    t = threading.Thread(target=run_source)
    t.start()
    reason = sink.run()
    t.join(5)
    assert not errors, errors
    assert events == ["play", "stop"]
    assert sink.playing and sink.session == "6B8B4567"
    assert reason == "demandé par la source"
    assert sink.formats["wfd_audio_codecs"] == "AAC 00000001 00"


def test_session_ends_when_source_disappears():
    sink_sock, source_sock = socket.socketpair()
    stops = []
    sink = RtspSink(sink_sock, "192.168.173.80", "TV", on_stop=lambda: stops.append(1))
    source_sock.close()
    assert sink.run() == "connexion fermée par la source"
    assert stops == [1]


def test_keepalive_timeout():
    sink_sock, source_sock = socket.socketpair()
    now = [0.0]
    sink = RtspSink(sink_sock, "x", "TV", clock=lambda: now[0])
    now[0] = 1000.0
    assert sink.run() == "plus de nouvelles de la source"
    source_sock.close()


# --- Lecteur ---------------------------------------------------------------------


def test_decoder_choice():
    assert pipeline.choose_decoder("Raspberry Pi 3 Model B Rev 1.2", True) == "v4l2h264dec"
    assert pipeline.choose_decoder("Raspberry Pi 5 Model B Rev 1.0", True) == "avdec_h264"
    assert pipeline.choose_decoder("Raspberry Pi 3 Model B", False) == "avdec_h264"


def test_pipeline_command():
    cmd = pipeline.build_command("v4l2h264dec", "plughw:CARD=vc4hdmi,DEV=0")
    text = " ".join(cmd)
    assert cmd[:3] == ["gst-launch-1.0", "-q", "-e"]
    assert "udpsrc" in cmd and "port=1028" in cmd
    assert "caps=application/x-rtp,media=video,clock-rate=90000,encoding-name=MP2T" in cmd
    assert "! capssetter caps=video/x-h264,profile=(string)high ! v4l2h264dec !" in text
    assert "kmssink sync=false can-scale=false" in text
    assert "device=plughw:CARD=vc4hdmi,DEV=0" in text and "avdec_aac" in text


CARDS = """ 0 [Headphones     ]: bcm2835_headpho - bcm2835 Headphones
                      bcm2835 Headphones
 1 [vc4hdmi        ]: vc4-hdmi - vc4-hdmi
                      vc4-hdmi
"""


def test_alsa_device():
    assert audio.alsa_device("hdmi", CARDS) == "plughw:CARD=vc4hdmi,DEV=0"
    assert audio.alsa_device("jack", CARDS) == "plughw:CARD=Headphones,DEV=0"
    assert audio.alsa_device("hdmi", "") is None


# --- AirPlay ---------------------------------------------------------------------


def test_airplay_pin_is_created_once(tmp_path):
    pin = airplay.load_pin(tmp_path)
    assert len(pin) == 4 and pin.isdigit() and pin != "0000"
    assert airplay.load_pin(tmp_path) == pin


def test_uxplay_command():
    cmd = airplay.build_command("TV Salon", "4821", "plughw:CARD=vc4hdmi,DEV=0", "v4l2h264dec")
    assert cmd[:3] == ["stdbuf", "-oL", "-eL"]  # messages d'UxPlay en direct
    assert cmd[3:8] == ["uxplay", "-n", "TV Salon", "-nh", "-pin"] and cmd[8] == "4821"
    assert "-p" in cmd and "-bt709" in cmd and "-avdec" not in cmd
    assert cmd[cmd.index("-vd") + 1] == "v4l2h264dec"
    assert cmd[cmd.index("-vc") + 1] == "v4l2convert"
    assert cmd[cmd.index("-vsync") + 1] == "no"
    assert cmd[cmd.index("-vs") + 1].startswith("kmssink")
    assert "-avdec" in airplay.build_command("X", "1111", None, "avdec_h264")


TCP = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid
   0: 2A01A8C0:1B58 1E01A8C0:C350 01 00000000:00000000 00:00000000 00000000   999
   1: 2A01A8C0:1BBC 1E01A8C0:C351 01 00000000:00000000 00:00000000 00000000   999
   2: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0
"""


def test_established_ports_and_state():
    ports = airplay.established_ports(TCP)
    assert ports == {7000, 7100}  # 0x1B58 = 7000, 0x1BBC = 7100 ; l'écoute (0A) ignorée
    assert airplay.decide_state(ports, None, 0) == "casting"
    assert airplay.decide_state({7000}, 100.0, 110.0) == "pin"
    assert airplay.decide_state({7000}, None, 0) == "connecting"
    assert airplay.decide_state(set(), 0.0, 1000.0) == "ready"


def test_pin_art_detection():
    assert airplay.is_pin_art('  d8888b.   .d8888b.   888    888   d8888b.')
    assert not airplay.is_pin_art("connection request from iPhone (iPhone14,2)")
    assert not airplay.is_pin_art("        ")


# --- État partagé et écran -----------------------------------------------------------


def test_cast_state_roundtrip_and_stale(tmp_path):
    cast_state.write("miracast", "casting", run_dir=tmp_path, now=100.0)
    assert cast_state.read("miracast", tmp_path, now=105.0)["state"] == "casting"
    assert cast_state.other_is_casting("airplay", tmp_path, now=105.0)
    assert cast_state.read("miracast", tmp_path, now=200.0)["state"] == "ready"  # périmé
    assert cast_state.read("airplay", tmp_path) == {}
    with pytest.raises(ValueError):
        cast_state.write("bluetooth", "ready", run_dir=tmp_path)


def test_bigdigits_aligned():
    lines = bigdigits.render("1234 5670")
    assert len(lines) == bigdigits.HEIGHT
    assert len({len(line) for line in lines}) == 1  # même largeur : reste aligné
    assert bigdigits.width("1234 5670") <= 60  # tient sur une TV en 720p (80 colonnes)


def test_screen_shows_codes_and_pin_request():
    info = Info(wifi_state="connected", ssid="Box", device_name="TV Salon",
                casts={"miracast": {"state": "ready", "pin": "1234 5670"},
                       "airplay": {"state": "ready", "pin": "4821"}})
    text = "\n".join(render_lines(info))
    assert "Windows + K" in text and "1234 5670" in text and "4821" in text

    casts = {"airplay": {"state": "pin", "pin": "4821", "peer": "iPhone de Zoé"},
             "miracast": {"state": "ready"}}
    assert pin_request(casts)[0] == "airplay"
    lines = pin_lines("airplay", casts["airplay"], "TV Salon")
    assert "iPhone" in lines[0] and "4821" in lines
    assert is_casting({"miracast": {"state": "casting"}})
    assert not is_casting(casts)


# --- Miracast over Infrastructure (MS-MICE) --------------------------------------------


def test_vendor_extension_matches_lazycast_format():
    from berrycast.miracast import mice

    ext = mice.vendor_extension("berrycast", "192.168.1.20")
    # lazycast : '0001372001000105' + '2002' + longueur + nom + '2005' + longueur + IP
    expected = ("000137" "2001" "0001" "05"
                "2002" "0009" + b"berrycast".hex()
                + "2005" "000c" + b"192.168.1.20".hex())
    assert ext.hex() == expected
    assert mice.vendor_extension("berrycast", None).hex().endswith(b"berrycast".hex())


def test_mice_parser():
    from berrycast.miracast import mice

    name = "PC-Salon".encode("utf-16-le")
    msg = mice.build_message(1, [(0, name), (2, (7236).to_bytes(2, "big"))])
    parser = mice.MiceParser()
    out = parser.feed(msg[:5]) + parser.feed(msg[5:] + mice.build_message(2))
    assert [m.command for m in out] == ["SOURCE_READY", "STOP_PROJECTION"]
    assert out[0].rtsp_port == 7236 and out[0].friendly_name == "PC-Salon"


def test_mice_server_end_to_end():
    import socket as sk

    from berrycast.miracast import mice

    events, done = [], threading.Event()
    server = mice.MiceServer(lambda ip, port, name: events.append(("ready", ip, port, name)),
                             lambda: (events.append(("stop",)), done.set()), port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sk.create_connection(("127.0.0.1", server.port), timeout=3) as client:
            client.sendall(mice.build_message(1, [(0, "PC".encode("utf-16-le")),
                                                  (2, (7236).to_bytes(2, "big"))]))
            client.sendall(mice.build_message(2))
            assert done.wait(3)
    finally:
        server.close()
    assert events[0] == ("ready", "127.0.0.1", 7236, "PC")
    assert ("stop",) in events


def test_container_id_and_avahi_file():
    from berrycast.miracast import mice

    cid = mice.container_id("0123456789abcdef0123456789abcdef" + chr(10))
    assert cid == mice.container_id("0123456789abcdef0123456789abcdef")  # stable
    assert len(cid) == 36 and cid.upper() == cid
    xml = mice.avahi_service(cid)
    assert "<type>_display._tcp</type>" in xml and "<port>7250</port>" in xml
    assert f"container_id={{{cid}}}" in xml


def test_parse_ipv4():
    out = "3: wlan0    inet 192.168.1.20/24 brd 192.168.1.255 scope global wlan0" + chr(10)
    assert parse_ipv4(out) == "192.168.1.20"
    assert parse_ipv4("") is None


def test_wait_screen_free(tmp_path):
    cast_state.write("airplay", "ready", run_dir=tmp_path)
    clock = [0.0]

    def sleep(seconds):
        clock[0] += seconds
        if clock[0] > 1:  # UxPlay s'arrête au bout d'une seconde
            cast_state.write("airplay", "off", run_dir=tmp_path)

    assert cast_state.wait_screen_free("miracast", 5, tmp_path, sleep, lambda: clock[0])
    assert 1 < clock[0] < 2
    cast_state.write("airplay", "ready", run_dir=tmp_path)
    assert not cast_state.wait_screen_free("miracast", 1, tmp_path,
                                           lambda s: clock.__setitem__(0, clock[0] + s),
                                           lambda: clock[0])
    cast_state.write("miracast", "connecting", run_dir=tmp_path)
    assert cast_state.other_wants_screen("airplay", tmp_path)


def test_idr_requested_again_while_player_starts():
    sink_sock, source_sock = socket.socketpair()
    now = [0.0]
    sink = RtspSink(sink_sock, "192.168.1.30", "TV", clock=lambda: now[0])
    sent = []
    sink.request_idr = lambda: sent.append(now[0])
    sink.session = "1"
    sink.pending["7"] = "PLAY"
    sink.handle_response(wfd.RtspMessage("RTSP/1.0 200 OK", {"cseq": "7"}))
    for t in (1.0, 2.0, 3.0, 6.0, 9.0, 20.0):
        now[0] = t
        sink.send_due_idr()
    assert sent == [0.0, 2.0, 3.0, 6.0, 9.0]  # prévues à 0 ; 1,5 ; 3 ; 5 ; 8 s
    sink_sock.close()
    source_sock.close()


def test_video_formats_limited_to_30fps_level_41():
    fields = wfd.VIDEO_FORMATS.split()
    assert fields[2] == "02" and fields[3] == "08"  # Constrained High, niveau 4.1
    assert int(fields[4], 16) == (1 << 0) | (1 << 5) | (1 << 7)  # 640x480p60, 720p30, 1080p30
    assert fields[5] == "00000000" and fields[6] == "00000000"  # ni VESA ni HH
