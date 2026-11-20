"""Lecture et validation du fichier berrycast-wifi.txt (image de développement).

Ce fichier se trouve sur la partition de démarrage de la carte microSD (celle qui
est visible dans l'Explorateur Windows). On l'édite avec le Bloc-notes :

    wifi_nom=MonIphone
    wifi_mot_de_passe=motdepasse
    pays=FR
    ssh_mot_de_passe=unAutreMotDePasse

Ce module ne fait que du traitement de texte (aucune action sur le système),
ce qui permet de le tester sur n'importe quel PC.
"""

from __future__ import annotations

import string
import unicodedata
from dataclasses import dataclass, field

from berrycast.countries import normalize_country

FILE_NAME = "berrycast-wifi.txt"

KEY_SSID = "wifi_nom"
KEY_PSK = "wifi_mot_de_passe"
KEY_COUNTRY = "pays"
KEY_SSH = "ssh_mot_de_passe"
KEYS = (KEY_SSID, KEY_PSK, KEY_COUNTRY, KEY_SSH)

MIN_SSH_PASSWORD = 8

# Modèle du fichier. {header} reçoit les messages (résultat de la dernière lecture).
TEMPLATE = """\
# ============================================================
#  BerryCast (image de développement) : réglages du Wi-Fi
# ============================================================
{header}#
# 1. Remplissez les lignes ci-dessous (après le signe =), sans guillemets.
# 2. Enregistrez (Bloc-notes : Fichier > Enregistrer), éjectez la carte,
#    mettez-la dans le Raspberry Pi et branchez-le.
#
# wifi_nom          : nom exact du réseau Wi-Fi (attention aux majuscules)
# wifi_mot_de_passe : mot de passe du Wi-Fi (vide = réseau sans mot de passe)
# pays              : pays où se trouve le Raspberry Pi, code à 2 lettres
#                     (norme ISO 3166, majuscules ou minuscules). Exemples :
#                     CH Suisse, FR France, BE Belgique, CA Canada,
#                     US États-Unis, DE Allemagne, GB Royaume-Uni, ES Espagne
#                     Liste complète : https://fr.wikipedia.org/wiki/ISO_3166-1_alpha-2
#                     Vide ou inconnu : réglage Wi-Fi international (fonctionne,
#                     mais certains canaux sont désactivés).
# ssh_mot_de_passe  : mot de passe de l'utilisateur « pi » pour SSH
#                     (8 caractères minimum)
#
# Sécurité : une fois les réglages appliqués, le Raspberry Pi EFFACE les
# mots de passe de ce fichier. Pour les changer, remplissez-les à nouveau.

{KEY_SSID}={ssid}
{KEY_PSK}=
{KEY_COUNTRY}={country}
{KEY_SSH}=
"""


@dataclass
class DevSettings:
    """Réglages valides extraits du fichier (None = non renseigné)."""

    ssid: str | None = None
    psk: str | None = None  # None ou "" = réseau ouvert (sans mot de passe)
    country: str | None = None  # code ISO valide, ou None = réglage international
    country_invalid: str | None = None  # ce qui a été tapé, si ce n'est pas un code valide
    ssh_password: str | None = None
    errors: list[str] = field(default_factory=list)  # bloquant pour la ligne concernée
    warnings: list[str] = field(default_factory=list)  # non bloquant

    def has_secrets(self) -> bool:
        return bool(self.psk or self.ssh_password)


def parse(text: str) -> dict[str, str]:
    """Lit les lignes « clé=valeur ». Ignore les commentaires (#) et les lignes vides.

    Tolère ce que produit le Bloc-notes de Windows : BOM UTF-8, fins de ligne CRLF.
    Les espaces autour de la clé et de la valeur sont retirés.
    """
    values: dict[str, str] = {}
    text = text.lstrip("﻿")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        if key in KEYS:
            values[key] = value.strip()
    return values


def _is_valid_psk(psk: str) -> bool:
    """Mot de passe WPA : 8 à 63 caractères ASCII imprimables, ou 64 chiffres hexadécimaux."""
    if len(psk) == 64 and all(c in string.hexdigits for c in psk):
        return True
    return 8 <= len(psk) <= 63 and all(32 <= ord(c) <= 126 for c in psk)


def validate(values: dict[str, str]) -> DevSettings:
    """Vérifie les valeurs lues et les convertit en réglages (avec messages d'erreur)."""
    s = DevSettings()

    # Pays : jamais bloquant. Vide ou inconnu -> réglage Wi-Fi international + avertissement.
    typed_country = values.get(KEY_COUNTRY, "")
    s.country = normalize_country(typed_country)
    if typed_country and s.country is None:
        s.country_invalid = typed_country
        s.warnings.append(
            f"pays « {typed_country} » inconnu : réglage Wi-Fi international utilisé"
        )

    ssid = values.get(KEY_SSID, "")
    psk = values.get(KEY_PSK, "")
    if ssid:
        if len(ssid.encode("utf-8")) > 32:
            s.errors.append("nom du Wi-Fi trop long (32 octets maximum)")
        elif psk and not _is_valid_psk(psk):
            s.errors.append("mot de passe Wi-Fi invalide (8 à 63 caractères, sans accent)")
        else:
            s.ssid = ssid
            s.psk = psk or None
            if not typed_country:
                s.warnings.append("pays non renseigné : réglage Wi-Fi international utilisé")
    elif psk:
        s.errors.append("mot de passe Wi-Fi donné sans nom de Wi-Fi")

    ssh = values.get(KEY_SSH, "")
    if ssh:
        if len(ssh) < MIN_SSH_PASSWORD:
            s.errors.append(f"mot de passe SSH trop court ({MIN_SSH_PASSWORD} caractères minimum)")
        elif ":" in ssh:
            # chpasswd utilise « : » comme séparateur utilisateur:motdepasse
            s.errors.append("le mot de passe SSH ne doit pas contenir « : »")
        else:
            s.ssh_password = ssh

    return s


def normalize_ssid(name: str) -> str:
    """Forme « tolérante » d'un nom de Wi-Fi, pour comparer ce que l'on a tapé et ce qui existe.

    Exemple : le partage de connexion d'un iPhone s'appelle souvent « iPhone de X »
    avec une apostrophe typographique (’), alors qu'au clavier on tape « ' ».
    """
    name = unicodedata.normalize("NFC", name)
    for fancy in "’‘ʼ`´":
        name = name.replace(fancy, "'")
    for fancy in "“”«»":
        name = name.replace(fancy, '"')
    return " ".join(name.split()).casefold()


def pick_ssid(typed: str, visible: list[str]) -> str:
    """Choisit le vrai nom du réseau parmi ceux détectés.

    - nom exact trouvé -> on le garde ;
    - sinon, un seul réseau visible a la même forme « tolérante » -> on prend celui-là ;
    - sinon -> on garde ce qui a été tapé (le réseau est peut-être éteint pour l'instant).
    """
    if typed in visible:
        return typed
    target = normalize_ssid(typed)
    matches = {v for v in visible if v and normalize_ssid(v) == target}
    if len(matches) == 1:
        return matches.pop()
    return typed


def render(ssid: str = "", country: str = "", messages: list[str] | None = None) -> str:
    """Produit le contenu du fichier, SANS aucun mot de passe.

    `messages` est affiché en haut du fichier (résultat de la dernière lecture).
    Les fins de ligne sont CRLF pour que le Bloc-notes de Windows l'affiche bien.
    """
    header = "".join(f"# >>> {m}\n" for m in (messages or []))
    content = TEMPLATE.format(
        header=header,
        KEY_SSID=KEY_SSID,
        KEY_PSK=KEY_PSK,
        KEY_COUNTRY=KEY_COUNTRY,
        KEY_SSH=KEY_SSH,
        ssid=ssid,
        country=country,
    )
    return content.replace("\n", "\r\n")
