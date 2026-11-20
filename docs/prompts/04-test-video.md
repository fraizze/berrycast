# Prompt 04 — Test de faisabilité n°3 : afficher la vidéo

Lis CLAUDE.md et les rapports dans `docs/recherche/`. Prototype dans `spikes/03-video/`.

Objectif : afficher le flux Miracast en plein écran sur l'HDMI du Pi 3, **sans bureau**, avec le son, de façon fluide.

À faire :
1. Liste les paquets GStreamer Debian nécessaires et une commande d'installation.
2. Pipeline GStreamer pour lire le fichier `.ts` enregistré à l'étape 03 : démultiplexage MPEG-TS → H.264 → décodage (`v4l2h264dec` sur Pi 3/4/Zero 2 W, `avdec_h264` sur Pi 5) → `kmssink` plein écran ; audio → `alsasink` sur HDMI.
3. Puis le même pipeline **en direct** depuis le flux RTP UDP pendant une vraie diffusion Windows + K (avec un petit tampon de gigue, latence la plus basse possible).
4. Mesure : images perdues, latence ressentie, charge CPU (`top`), température. Teste 720p et 1080p.
5. Script de détection du modèle de Pi (`/proc/device-tree/model`) qui choisit automatiquement le bon décodeur.

**Critère de réussite** : l'écran de mon PC s'affiche sur la TV via le Pi, avec le son, latence < ~0,5 s en 720p ou 1080p30.
Rapport dans `docs/recherche/03-video.md` avec les chiffres mesurés et une **conclusion claire : on continue ou pas**.
