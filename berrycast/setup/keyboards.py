"""Dispositions de clavier proposées au premier lancement, et application immédiate.

L'application passe par les outils de la console Debian : « ckbcomp » (paquet
console-setup) traduit une disposition XKB en table pour la console, « loadkeys »
(paquet kbd) la charge sur tty1. Charger une table demande des droits root
(CAP_SYS_TTY_CONFIG ; vérifié sur le Pi : « Permission denied » sans root) : c'est donc
la partie root (berrycast.setup.apply) qui appelle apply(), à la demande de l'interface.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass


@dataclass(frozen=True)
class Layout:
    label: str
    layout: str  # disposition XKB
    variant: str = ""


LAYOUTS = (
    Layout("Suisse romand (QWERTZ)", "ch", "fr"),
    Layout("Suisse alémanique (QWERTZ)", "ch"),
    Layout("Français (AZERTY)", "fr"),
    Layout("Belge (AZERTY)", "be"),
    Layout("Canadien français", "ca"),
    Layout("Allemand (QWERTZ)", "de"),
    Layout("Italien", "it"),
    Layout("Espagnol", "es"),
    Layout("Anglais britannique (QWERTY)", "gb"),
    Layout("Anglais américain (QWERTY)", "us"),
)

# Disposition proposée en premier selon le pays détecté
DEFAULT_BY_COUNTRY = {
    "CH": 0, "FR": 2, "BE": 3, "CA": 4, "DE": 5, "AT": 5, "IT": 6, "ES": 7, "GB": 8, "US": 9,
}


def default_index(country: str | None) -> int:
    return DEFAULT_BY_COUNTRY.get(country or "", 2)


def is_safe(layout: str, variant: str) -> bool:
    """Noms XKB simples uniquement (ils sont passés à des commandes)."""
    return layout.isalpha() and len(layout) <= 8 and (variant == "" or variant.isalnum())


def apply(layout: Layout, console: str | None = None) -> tuple[bool, str]:
    """Charge la disposition dans la console (effet immédiat). Renvoie (réussi, erreur).

    `console` : périphérique à viser (« /dev/tty » = terminal de contrôle ; « /dev/tty1 »
    pour la partie root). La table passe par un fichier temporaire.
    """
    if not is_safe(layout.layout, layout.variant):
        return False, "disposition invalide"
    cmd = ["ckbcomp", "-layout", layout.layout]
    if layout.variant:
        cmd += ["-variant", layout.variant]
    try:
        keymap = subprocess.run(cmd, capture_output=True, timeout=30, check=True).stdout
    except subprocess.CalledProcessError as exc:
        return False, f"ckbcomp : {exc.stderr.decode(errors='replace').strip()}"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"ckbcomp : {exc}"

    fd, path = tempfile.mkstemp(prefix="berrycast-", suffix=".kmap")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(keymap)
        load = ["loadkeys", "-q", "-u"] + (["-C", console] if console else []) + [path]
        result = subprocess.run(load, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"loadkeys : {exc}"
    finally:
        os.unlink(path)
    if result.returncode != 0:
        return False, f"loadkeys : {result.stderr.decode(errors='replace').strip()}"
    return True, ""
