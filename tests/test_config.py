"""Tests de berrycast.config (lecture, écriture atomique, valeurs invalides)."""

import os

import pytest

from berrycast import config
from berrycast.config import Config


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    """Fait pointer BERRYCAST_CONFIG vers un fichier temporaire."""
    path = tmp_path / "etc" / "config.toml"
    monkeypatch.setenv(config.ENV_VAR, str(path))
    return path


def test_default_path_without_env(monkeypatch):
    monkeypatch.delenv(config.ENV_VAR, raising=False)
    assert config.config_path() == config.DEFAULT_PATH


def test_env_var_overrides_path(cfg_path):
    assert config.config_path() == cfg_path


def test_missing_file_gives_defaults(cfg_path):
    assert config.load() == Config()


def test_defaults_are_sensible():
    c = Config()
    assert c.language == "fr"
    assert c.audio_output == "hdmi"
    assert c.airplay_enabled is True
    assert c.miracast_enabled is True
    assert c.setup_done is False
    assert config.is_valid_device_name(c.device_name)


def test_save_then_load_roundtrip(cfg_path):
    original = Config(
        device_name="TV Salon",
        language="en",
        audio_output="jack",
        airplay_enabled=False,
        miracast_enabled=True,
        setup_done=True,
    )
    config.save(original)
    assert cfg_path.exists()  # le dossier parent a été créé
    assert config.load() == original


@pytest.mark.parametrize(
    "name",
    ['TV "Salon"', "C:\\chemin", "Télé de Zoé", "Écran 📺", "L'atelier # 2"],
)
def test_special_characters_roundtrip(cfg_path, name):
    config.save(Config(device_name=name))
    assert config.load().device_name == name


def test_file_written_is_valid_toml_with_lf(cfg_path):
    config.save(Config())
    raw = cfg_path.read_bytes()
    assert b"\r\n" not in raw
    assert b'device_name = "BerryCast"' in raw


def test_partial_file_keeps_defaults_for_missing_keys(cfg_path):
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text('device_name = "Bureau"\n', encoding="utf-8")
    c = config.load()
    assert c.device_name == "Bureau"
    assert c.language == "fr"
    assert c.setup_done is False


def test_invalid_values_fall_back_to_defaults(cfg_path):
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(
        'device_name = ""\n'
        'language = "de"\n'
        'audio_output = "bluetooth"\n'
        "airplay_enabled = 1\n"
        'setup_done = "oui"\n'
        'unknown_key = "x"\n',
        encoding="utf-8",
    )
    assert config.load() == Config()


def test_corrupt_file_gives_defaults(cfg_path):
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text("ceci n'est pas du TOML ===", encoding="utf-8")
    assert config.load() == Config()


def test_device_name_validation():
    assert config.is_valid_device_name("TV Salon")
    assert not config.is_valid_device_name("")
    assert not config.is_valid_device_name("   ")
    assert not config.is_valid_device_name("x" * (config.MAX_DEVICE_NAME_LENGTH + 1))
    assert not config.is_valid_device_name("ligne1\nligne2")
    assert not config.is_valid_device_name(42)


def test_save_rejects_invalid_values(cfg_path):
    with pytest.raises(ValueError):
        config.save(Config(language="de"))
    assert not cfg_path.exists()


def test_save_is_atomic_on_failure(cfg_path, monkeypatch):
    """Si le renommage échoue, l'ancien fichier reste intact et aucun temporaire ne traîne."""
    config.save(Config(device_name="Avant"))
    before = cfg_path.read_bytes()

    def failing_replace(src, dst):
        raise OSError("disque plein (simulé)")

    monkeypatch.setattr(config.os, "replace", failing_replace)
    with pytest.raises(OSError):
        config.save(Config(device_name="Après"))

    assert cfg_path.read_bytes() == before
    assert os.listdir(cfg_path.parent) == [cfg_path.name]


def test_save_leaves_no_temp_files(cfg_path):
    config.save(Config())
    config.save(Config(device_name="Autre"))
    assert os.listdir(cfg_path.parent) == [cfg_path.name]
