# Prompt 11 — Image prête à flasher (balenaEtcher)

Lis CLAUDE.md.

Objectif : publier dans les **Releases GitHub** un fichier `berrycast-<version>-arm64.img.xz` que n'importe qui flashe avec **balenaEtcher**, sans aucune autre étape.

À faire :
1. Vérifie l'outil officiel actuellement recommandé par Raspberry Pi pour construire une image personnalisée (**rpi-image-gen** ou **pi-gen**) et explique ton choix.
2. Image basée sur **Raspberry Pi OS Lite 64-bit** (dernière version) + BerryCast et toutes ses dépendances préinstallées + services activés + `setup_done = false`.
3. Aucun mot de passe par défaut connu : SSH **désactivé** par défaut (option activable depuis la page de réglages, avec création d'un mot de passe).
4. Premier démarrage : agrandissement de la partition, génération des clés SSH/identifiants uniques, puis écran `welcome_setup`.
5. Workflow GitHub Actions qui construit l'image (émulation arm64 si nécessaire), la compresse en `.xz`, calcule le SHA-256 et la publie sur une *Release* quand je crée un tag `vX.Y.Z`. Vérifie la limite de taille des fichiers de Release.
6. Garde aussi `scripts/install.sh` pour installer BerryCast sur un Raspberry Pi OS Lite déjà installé (pour les développeurs).
7. Mets à jour le README : télécharger → balenaEtcher (« Flash from file » → choisir la carte → « Flash! ») → brancher → suivre l'écran.

Critère de réussite : je flashe l'image de la Release sur ma microSD avec balenaEtcher, je branche mon Pi 3, et j'arrive à l'écran de bienvenue sans rien taper.
(Plus tard, en option : une image `armhf` pour le Pi Zero W.)
