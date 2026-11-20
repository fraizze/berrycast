"""Dispositions de clavier proposées au premier lancement, et application immédiate.

L'application passe par les outils de la console Debian : « ckbcomp » (paquet
console-setup) traduit une disposition XKB en table pour la console, « loadkeys »
(paquet kbd) la charge. Pas besoin de root : le noyau autorise le processus dont
c'est le terminal de contrôle (ici tty1, donné par systemd avec StandardInput=tty)
à changer la table du clavier. L'enregistrement définitif (/etc/default/keyboard)
se fera à l'étape « appliquer les réglages ».
"""

from __future__ import annotations

import subprocess
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


def apply(layout: Layout) -> bool:
    """Charge la disposition dans la console (effet immédiat sur le clavier). True si OK."""
    cmd = ["ckbcomp", "-layout", layout.layout]
    if layout.variant:
        cmd += ["-variant", layout.variant]
    try:
        keymap = subprocess.run(cmd, capture_output=True, timeout=20, check=True).stdout
        subprocess.run(["loadkeys", "-q", "-u"], input=keymap, capture_output=True,
                       timeout=20, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False
