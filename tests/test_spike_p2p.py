"""Tests des données construites par le prototype spikes/01-p2p/p2p_listen.py."""

import importlib.util
from pathlib import Path

SPIKE = Path(__file__).resolve().parent.parent / "spikes" / "01-p2p" / "p2p_listen.py"
spec = importlib.util.spec_from_file_location("p2p_listen", SPIKE)
p2p_listen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p2p_listen)


def test_wfd_device_info_subelement_bytes():
    # id 00 | longueur 0006 | device info 0011 (sink principal + disponible)
    # | port 1c44 (7236) | débit 0032 (50 Mb/s)
    assert p2p_listen.wfd_device_info_subelement().hex() == "00000600111c440032"


def test_wfd_subelement_is_long_enough_for_wpa_supplicant():
    # wifi_display_subelem_set_from_ies() refuse moins de 6 octets
    assert len(p2p_listen.wfd_device_info_subelement()) >= 6


def test_primary_device_type_is_display_tv():
    t = p2p_listen.PRIMARY_DEVICE_TYPE_TV
    assert len(t) == 8  # WPS_DEV_TYPE_LEN
    assert t[:2] == b"\x00\x07"  # catégorie 7 = écran
    assert t[2:6] == bytes.fromhex("0050f204")  # OUI Wi-Fi Alliance
    assert t[6:] == b"\x00\x01"  # sous-catégorie 1 = TV
