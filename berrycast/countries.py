"""Codes pays ISO 3166-1 alpha-2, pour le réglage du Wi-Fi (domaine réglementaire).

Chaque pays autorise des canaux et des puissances Wi-Fi différents. Le système
(noyau Linux + base « wireless-regdb ») utilise ces codes à 2 lettres. Sans pays
connu, on utilise le réglage international « 00 », plus prudent (certains canaux
désactivés) mais qui fonctionne partout.

Liste complète : https://fr.wikipedia.org/wiki/ISO_3166-1_alpha-2
Cette liste servira aussi à la liste déroulante du premier lancement (étape 06).
"""

from __future__ import annotations

# Réglage Wi-Fi international (« monde ») utilisé quand le pays est inconnu.
WORLD_REGDOMAIN = "00"

# Les 249 codes officiellement attribués par la norme ISO 3166-1.
ISO_3166_ALPHA2 = frozenset(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ
    BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
    CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ
    DE DJ DK DM DO DZ
    EC EE EG EH ER ES ET
    FI FJ FK FM FO FR
    GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY
    HK HM HN HR HT HU
    ID IE IL IM IN IO IQ IR IS IT
    JE JM JO JP
    KE KG KH KI KM KN KP KR KW KY KZ
    LA LB LC LI LK LR LS LT LU LV LY
    MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ
    NA NC NE NF NG NI NL NO NP NR NU NZ
    OM
    PA PE PF PG PH PK PL PM PN PR PS PT PW PY
    QA
    RE RO RS RU RW
    SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ
    TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ
    UA UG UM US UY UZ
    VA VC VE VG VI VN VU
    WF WS
    YE YT
    ZA ZM ZW
    """.split()
)


def normalize_country(code: str | None) -> str | None:
    """Renvoie le code en majuscules s'il est valide (« fr » -> « FR »), sinon None."""
    if not code:
        return None
    code = code.strip().upper()
    return code if code in ISO_3166_ALPHA2 else None


def parse_iw_reg_get(output: str) -> str | None:
    """Extrait le pays Wi-Fi actif de la sortie de « iw reg get ».

    Exemple de sortie :
        global
        country FR: DFS-ETSI
            (2400 - 2483 @ 40), (N/A, 20), (N/A)
    -> « FR » (ou « 00 » pour le réglage international). None si illisible.
    """
    lines = [line.strip() for line in output.splitlines()]
    for i, line in enumerate(lines):
        if line == "global" and i + 1 < len(lines):
            parts = lines[i + 1].split()
            if len(parts) >= 2 and parts[0] == "country":
                return parts[1].rstrip(":")
    return None
