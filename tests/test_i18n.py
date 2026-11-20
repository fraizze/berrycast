"""Tests de berrycast.i18n (traductions)."""

import pytest

from berrycast import i18n
from berrycast.i18n import t


@pytest.fixture(autouse=True)
def reset_language():
    """Remet la langue par défaut après chaque test."""
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


def test_all_languages_have_the_same_keys():
    reference = set(i18n.load_messages("fr"))
    for language in i18n.LANGUAGES:
        assert set(i18n.load_messages(language)) == reference, language


def test_no_empty_translation():
    for language in i18n.LANGUAGES:
        for key, text in i18n.load_messages(language).items():
            assert text.strip(), f"{language}:{key} est vide"


def test_french_is_default():
    assert i18n.get_language() == "fr"
    assert t("ready") == "Prêt à recevoir"


def test_switch_to_english():
    i18n.set_language("en")
    assert t("ready") == "Ready to receive"


def test_explicit_language_argument():
    assert t("welcome", language="en") == "Welcome"
    assert i18n.get_language() == "fr"


def test_parameters_are_substituted():
    assert t("settings_address", url="http://tv-salon.local") == (
        "Réglages : http://tv-salon.local"
    )


def test_missing_parameter_does_not_crash():
    assert t("settings_address") == "Réglages : {url}"
    assert t("settings_address", wrong="x") == "Réglages : {url}"


def test_unknown_key_returns_key():
    assert t("cle_qui_n_existe_pas") == "cle_qui_n_existe_pas"


def test_unknown_language_is_refused():
    with pytest.raises(ValueError):
        i18n.set_language("de")
    with pytest.raises(ValueError):
        t("ready", language="de")
