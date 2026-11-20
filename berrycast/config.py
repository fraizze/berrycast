"""Lecture et écriture de la configuration de BerryCast.

Le fichier est un TOML simple (une clé = une valeur, pas de sections), par défaut
dans /etc/berrycast/config.toml. Pour les tests ou le développement, on peut
changer ce chemin avec la variable d'environnement BERRYCAST_CONFIG.

Principes :
- un fichier absent, illisible ou une valeur invalide ne doit JAMAIS faire planter
  l'appareil : on revient aux valeurs par défaut (et on le signale dans les logs) ;
- l'écriture est atomique (fichier temporaire puis renommage) : une coupure de
  courant pendant l'enregistrement ne laisse jamais un fichier à moitié écrit.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_PATH = Path("/etc/berrycast/config.toml")
ENV_VAR = "BERRYCAST_CONFIG"

LANGUAGES = ("fr", "en")
AUDIO_OUTPUTS = ("hdmi", "jack")

# Longueur maximale du nom de l'appareil, en caractères.
# Le nom Wi-Fi Direct (WPS « Device Name ») est limité à 32 octets : à confirmer
# et à affiner (octets UTF-8 vs caractères) lors de l'étape Miracast.
MAX_DEVICE_NAME_LENGTH = 32


@dataclass
class Config:
    """Réglages de l'appareil, avec leurs valeurs par défaut."""

    device_name: str = "BerryCast"
    language: str = "fr"
    audio_output: str = "hdmi"
    airplay_enabled: bool = True
    miracast_enabled: bool = True
    setup_done: bool = False


def config_path() -> Path:
    """Chemin du fichier de configuration (surchargeable par BERRYCAST_CONFIG)."""
    override = os.environ.get(ENV_VAR)
    return Path(override) if override else DEFAULT_PATH


def is_valid_device_name(name: object) -> bool:
    """Un nom valide : du texte non vide, pas trop long, sans caractère de contrôle."""
    if not isinstance(name, str):
        return False
    stripped = name.strip()
    if not stripped or len(stripped) > MAX_DEVICE_NAME_LENGTH:
        return False
    return all(ch.isprintable() for ch in stripped)


def _validate(key: str, value: object) -> bool:
    """Indique si `value` est acceptable pour le champ `key`."""
    if key == "device_name":
        return is_valid_device_name(value)
    if key == "language":
        return value in LANGUAGES
    if key == "audio_output":
        return value in AUDIO_OUTPUTS
    # Les autres champs sont des booléens.
    # Attention : en Python, bool est une sous-classe de int, mais pas l'inverse,
    # donc 1 ou 0 sont bien refusés ici.
    return isinstance(value, bool)


def load(path: Path | None = None) -> Config:
    """Lit la configuration. Ne lève jamais d'exception : au pire, valeurs par défaut."""
    path = path or config_path()
    defaults = Config()

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        log.info("Pas de fichier de configuration (%s) : valeurs par défaut.", path)
        return defaults
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.warning("Configuration illisible (%s) : %s. Valeurs par défaut.", path, exc)
        return defaults

    values = {}
    for field in dataclasses.fields(Config):
        if field.name not in data:
            continue
        value = data[field.name]
        if _validate(field.name, value):
            values[field.name] = value.strip() if isinstance(value, str) else value
        else:
            log.warning(
                "Valeur invalide pour %r dans %s : %r. Valeur par défaut utilisée.",
                field.name,
                path,
                value,
            )

    unknown = set(data) - {f.name for f in dataclasses.fields(Config)}
    if unknown:
        log.warning("Clés inconnues ignorées dans %s : %s", path, ", ".join(sorted(unknown)))

    return dataclasses.replace(defaults, **values)


def _toml_value(value: object) -> str:
    """Convertit une valeur simple (str ou bool) en texte TOML."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        # Une chaîne JSON est une chaîne TOML valide (mêmes échappements \" \\ \n \uXXXX…),
        # sauf le caractère DEL (U+007F) que TOML exige d'échapper et que JSON laisse tel quel.
        return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")
    raise TypeError(f"Type non pris en charge dans la configuration : {type(value).__name__}")


def dumps(config: Config) -> str:
    """Produit le texte TOML correspondant à la configuration."""
    lines = ["# Configuration de BerryCast (fichier généré automatiquement)"]
    for field in dataclasses.fields(Config):
        lines.append(f"{field.name} = {_toml_value(getattr(config, field.name))}")
    return "\n".join(lines) + "\n"


def save(config: Config, path: Path | None = None) -> None:
    """Enregistre la configuration de façon atomique.

    Étapes : écrire dans un fichier temporaire du MÊME dossier, forcer l'écriture
    sur le disque (fsync), puis remplacer l'ancien fichier d'un coup (os.replace).
    """
    for field in dataclasses.fields(Config):
        value = getattr(config, field.name)
        if not _validate(field.name, value):
            raise ValueError(f"Valeur invalide pour {field.name!r} : {value!r}")

    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = dumps(config)

    fd, tmp_name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        # mkstemp crée le fichier en 0600 ; la configuration ne contient pas de secret,
        # on la rend lisible par tous (les mots de passe Wi-Fi restent dans NetworkManager).
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    except BaseException:
        # En cas d'erreur, on supprime le fichier temporaire : l'ancien fichier reste intact.
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise

    _fsync_directory(path.parent)


def _fsync_directory(directory: Path) -> None:
    """Force l'enregistrement du renommage sur le disque (Linux uniquement)."""
    if os.name != "posix":
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
