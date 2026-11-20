"""Tests des codes pays ISO 3166-1 (réglage Wi-Fi)."""

import pytest

from berrycast.countries import (
    ISO_3166_ALPHA2,
    WORLD_REGDOMAIN,
    normalize_country,
    parse_iw_reg_get,
)


def test_list_has_all_249_codes():
    assert len(ISO_3166_ALPHA2) == 249
    assert all(len(c) == 2 and c.isascii() and c.isupper() for c in ISO_3166_ALPHA2)


@pytest.mark.parametrize("code", ["CH", "FR", "BE", "CA", "US", "DE", "GB", "JP", "BR", "ZA"])
def test_examples_are_valid(code):
    assert normalize_country(code) == code


@pytest.mark.parametrize("typed,expected", [("fr", "FR"), (" ch ", "CH"), ("Be", "BE")])
def test_lowercase_and_spaces_accepted(typed, expected):
    assert normalize_country(typed) == expected


@pytest.mark.parametrize("typed", ["", None, "France", "F", "XX", "UK", "EU", "00", "1A", "É"])
def test_invalid_codes(typed):
    # « UK » et « EU » ne sont pas des codes ISO 3166-1 attribués (Royaume-Uni = GB)
    assert normalize_country(typed) is None


def test_world_is_not_a_country():
    assert WORLD_REGDOMAIN not in ISO_3166_ALPHA2


def test_parse_iw_reg_get():
    out = "global\ncountry FR: DFS-ETSI\n\t(2400 - 2483 @ 40), (N/A, 20), (N/A)\n"
    assert parse_iw_reg_get(out) == "FR"
    assert parse_iw_reg_get("global\ncountry 00: DFS-UNSET\n") == "00"
    assert parse_iw_reg_get("") is None
    assert parse_iw_reg_get("phy#0\ncountry 99: invalid\n") is None
