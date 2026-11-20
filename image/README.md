# image/

Construction des images à flasher avec **balenaEtcher**.

## Image de développement (`berrycast-dev-<date>-<commit>.img.xz`)

Construite par GitHub Actions ([`.github/workflows/image-dev.yml`](../.github/workflows/image-dev.yml))
à chaque envoi sur `main`, et publiée dans la pré-version **« dev »** des *Releases*.

- Outil : **pi-gen**, l'outil officiel avec lequel Raspberry Pi construit Raspberry Pi OS
  (branche `arm64`, Debian 13 « Trixie »), lancé dans Docker sur une machine ARM 64 bits de GitHub.
- Base : stages 0 à 2 de pi-gen = **Raspberry Pi OS Lite 64 bits**.
- Notre ajout : [`pi-gen/stage-berrycast/`](pi-gen/stage-berrycast/) (code du dépôt dans `/opt/berrycast`,
  services `system/dev/` dont la configuration au clavier sur la TV, fichier de secours
  `berrycast-wifi.txt` sur la partition de démarrage). Paquets : `00-packages` (avec recommandés)
  et `00-packages-nr` (sans les paquets recommandés, pour garder l'image légère).
- Réglages : [`pi-gen/config`](pi-gen/config) (utilisateur `pi`, nom d'hôte `berrycast`, SSH activé,
  aucun mot de passe connu).

Mode d'emploi : [`docs/image-dev.md`](../docs/image-dev.md).

## Image finale (étape 11)

À venir : image « utilisateur final », sans SSH, avec l'assistant de premier lancement.
