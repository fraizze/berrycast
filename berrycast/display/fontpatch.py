"""Ajoute le caractère « ▀ » (demi-bloc haut, U+2580) à une police console PSF.

Pourquoi : pour dessiner un QR code net sur la TV, chaque caractère affiche deux
« pixels » du QR l'un au-dessus de l'autre (« ▀ » avec la couleur du texte en haut et
la couleur du fond en bas). Les polices console latines de Debian (Lat15, Uni2) n'ont
pas ce caractère (vérifié dans console-setup : seul le bloc plein « █ » existe).

On remplace donc le dessin d'un caractère inutile ici, « ░ » (U+2591, trame légère),
par un demi-bloc haut, et on l'associe à U+2580.

Utilisation (à la construction de l'image, ou sur le Pi) :
    python3 -m berrycast.display.fontpatch SOURCE.psf.gz DESTINATION.psf
"""

from __future__ import annotations

import gzip
import struct
import sys
from pathlib import Path

PSF2_MAGIC = 0x864AB572
PSF2_HAS_UNICODE_TABLE = 0x01
UPPER_HALF_BLOCK = "▀"
SACRIFICED_CHAR = "░"  # « ░ », jamais utilisé par BerryCast


class FontError(ValueError):
    pass


def _parse_unicode_table(data: bytes, count: int) -> list[list[str]]:
    """Table PSF2 : pour chaque glyphe, des caractères UTF-8 ; 0xFE = séquence, 0xFF = fin."""
    entries: list[list[str]] = []
    pos = 0
    for _ in range(count):
        end = data.index(b"\xff", pos)
        raw = data[pos:end]
        chars = raw.split(b"\xfe")[0].decode("utf-8")  # on ignore les séquences combinées
        seqs = raw.split(b"\xfe")[1:]
        entries.append(list(chars) + [s.decode("utf-8") for s in seqs if s])
        pos = end + 1
    return entries


def _build_unicode_table(entries: list[list[str]]) -> bytes:
    out = bytearray()
    for chars in entries:
        singles = "".join(c for c in chars if len(c) == 1)
        out += singles.encode("utf-8")
        for seq in (c for c in chars if len(c) > 1):
            out += b"\xfe" + seq.encode("utf-8")
        out += b"\xff"
    return bytes(out)


def add_upper_half_block(font: bytes) -> bytes:
    """Renvoie une police PSF2 où « ░ » est redessiné en « ▀ » (U+2580)."""
    if len(font) < 32:
        raise FontError("fichier trop court")
    magic, _version, header_size, flags, count, charsize, height, width = struct.unpack(
        "<IIIIIIII", font[:32]
    )
    if magic != PSF2_MAGIC:
        raise FontError("ce n'est pas une police PSF2")
    if not flags & PSF2_HAS_UNICODE_TABLE:
        raise FontError("la police n'a pas de table Unicode")

    glyphs_end = header_size + count * charsize
    glyphs = bytearray(font[header_size:glyphs_end])
    table = _parse_unicode_table(font[glyphs_end:], count)

    if any(UPPER_HALF_BLOCK in chars for chars in table):
        return font  # déjà présent : rien à faire

    try:
        index = next(i for i, chars in enumerate(table) if SACRIFICED_CHAR in chars)
    except StopIteration:
        raise FontError("caractère « ░ » introuvable dans la police") from None

    # Dessin : moitié haute pleine, moitié basse vide
    row_bytes = (width + 7) // 8
    full_row = bytearray(b"\xff" * row_bytes)
    if width % 8:
        full_row[-1] = (0xFF << (8 - width % 8)) & 0xFF
    bitmap = bytearray(charsize)
    for row in range(height // 2):
        bitmap[row * row_bytes:(row + 1) * row_bytes] = full_row
    glyphs[index * charsize:(index + 1) * charsize] = bitmap
    table[index] = [UPPER_HALF_BLOCK]

    return font[:header_size] + bytes(glyphs) + _build_unicode_table(table)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    source, destination = Path(argv[0]), Path(argv[1])
    raw = source.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(add_upper_half_block(raw))
    print(f"Police écrite : {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
