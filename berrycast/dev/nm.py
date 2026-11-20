"""Petits utilitaires pour lire la sortie de nmcli (NetworkManager)."""

from __future__ import annotations


def split_terse(line: str) -> list[str]:
    """Découpe une ligne « nmcli -t » (champs séparés par « : »).

    En mode -t, nmcli échappe « : » et « \\ » à l'intérieur des valeurs avec « \\ ».
    Exemple : « wlan0:wifi:connected:Box\\:Salon » -> ["wlan0", "wifi", "connected", "Box:Salon"].
    """
    fields: list[str] = []
    current: list[str] = []
    chars = iter(line)
    for ch in chars:
        if ch == "\\":
            current.append(next(chars, ""))
        elif ch == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)
    fields.append("".join(current))
    return fields
