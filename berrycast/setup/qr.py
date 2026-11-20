"""QR code « rejoindre ce Wi-Fi », dessiné en texte sur la console de la TV.

Chaque caractère « ▀ » affiche 2 modules du QR l'un au-dessus de l'autre :
couleur du texte = module du haut, couleur du fond = module du bas. Avec une police
16x32, un module fait donc 16x16 pixels (carré). La police doit contenir « ▀ »
(voir berrycast.display.fontpatch).

Le QR code est clair (gris) avec des modules noirs, entouré d'une marge claire :
c'est ce que les appareils photo des téléphones lisent le mieux.
"""

from __future__ import annotations

UPPER_HALF_BLOCK = "▀"
BLACK, LIGHT = 0, 7  # couleurs de la console Linux (7 = gris clair)
QUIET_ZONE = 2  # marge claire autour du QR (en modules)


def _escape(value: str) -> str:
    """Échappement du format « WIFI: » : \\ ; , : et " sont précédés de \\."""
    for ch in '\\;,:"':
        value = value.replace(ch, "\\" + ch)
    return value


def wifi_payload(ssid: str, password: str | None) -> str:
    """Texte du QR code que les téléphones (iPhone, Android) savent rejoindre."""
    if password:
        return f"WIFI:T:WPA;S:{_escape(ssid)};P:{_escape(password)};;"
    return f"WIFI:T:nopass;S:{_escape(ssid)};;"


def qr_matrix(text: str) -> list[list[bool]]:
    """Matrice du QR code (True = module noir), sans marge. Utilise python3-qrcode."""
    import qrcode  # paquet Debian python3-qrcode

    # Correction d'erreur « L » : QR plus petit (29x29 au lieu de 33x33), assez pour un
    # écran net ; il tient à côté du texte même sur une TV en 720p (80 colonnes).
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, border=0)
    qr.add_data(text)
    qr.make(fit=True)
    return [list(row) for row in qr.get_matrix()]


def to_terminal_lines(matrix: list[list[bool]], quiet: int = QUIET_ZONE) -> list[str]:
    """Convertit la matrice en lignes de texte avec couleurs ANSI (2 rangées par ligne).

    Chaque ligne fait exactement len(matrix) + 2 * quiet caractères visibles.
    """
    size = len(matrix) + 2 * quiet
    padded = [[False] * size for _ in range(quiet)]
    padded += [[False] * quiet + list(row) + [False] * quiet for row in matrix]
    padded += [[False] * size for _ in range(quiet)]
    if len(padded) % 2:
        padded.append([False] * size)

    lines = []
    for top, bottom in zip(padded[0::2], padded[1::2], strict=True):
        out, current = [], None
        for t, b in zip(top, bottom, strict=True):
            colors = (BLACK if t else LIGHT, BLACK if b else LIGHT)
            if colors != current:
                out.append(f"\033[3{colors[0]};4{colors[1]}m")
                current = colors
            out.append(UPPER_HALF_BLOCK)
        out.append("\033[0m")
        lines.append("".join(out))
    return lines


def visible_width(matrix: list[list[bool]], quiet: int = QUIET_ZONE) -> int:
    return len(matrix) + 2 * quiet
