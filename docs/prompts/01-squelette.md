# Prompt 01 — Squelette du dépôt

Lis d'abord CLAUDE.md en entier.

Crée la base du dépôt BerryCast, sans encore écrire la logique Miracast/AirPlay :

1. L'arborescence décrite dans CLAUDE.md (dossiers avec un petit `README.md` ou `__init__.py` pour expliquer leur rôle).
2. `LICENSE` (texte officiel GPL-3.0).
3. `README.md` (français) et `README.en.md` (anglais) orientés **utilisateur final** :
   - ce que fait BerryCast, les modèles supportés (tableau de CLAUDE.md),
   - installation : télécharger l'image dans les Releases → flasher avec **balenaEtcher** (étapes simples) → brancher le Pi en HDMI → suivre l'écran,
   - limites connues (pas de HDCP/Netflix, une diffusion à la fois),
   - section « Statut : en développement ».
4. `berrycast/config.py` : lecture/écriture d'un fichier `/etc/berrycast/config.toml` (chemin surchargeable par variable d'environnement pour les tests). Champs : `device_name`, `language`, `audio_output` (`hdmi`|`jack`), `airplay_enabled`, `miracast_enabled`, `setup_done`. Valeurs par défaut sensées. Écriture **atomique** (fichier temporaire + rename).
5. `berrycast/i18n/` avec `fr.json` et `en.json` + une petite fonction `t("cle")`.
6. `tests/` avec pytest pour config et i18n.
7. GitHub Actions : un workflow qui lance pytest + un linter (ruff) à chaque push.
8. `.gitignore`, `CONTRIBUTING.md` court.

À la fin : liste des fichiers créés, et comment lancer les tests sur mon PC.
