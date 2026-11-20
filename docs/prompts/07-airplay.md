# Prompt 07 — AirPlay (Recopie de l'écran iPhone)

Lis CLAUDE.md. Code dans `berrycast/airplay/`.

Objectif : depuis mon iPhone (même Wi-Fi que le Pi), « Recopie de l'écran » → le nom de l'appareil apparaît → l'écran de l'iPhone s'affiche sur la TV avec le son.

À faire :
1. Installer **UxPlay** depuis les paquets Debian + plugins GStreamer nécessaires. Vérifie la version disponible et ses options (`uxplay -h`).
2. Lancer UxPlay avec les bons réglages selon le modèle : nom de l'appareil (sans suffixe `@hostname`), sortie vidéo `kmssink`, décodeur adapté (matériel ou logiciel selon le modèle, voir rapport 03), sortie audio selon `audio_output`.
3. **Code de vérification** : utiliser l'appairage par code d'UxPlay (option PIN si disponible). Capturer le code et l'afficher en grand via l'écran `pin`. Si l'option n'existe pas dans la version Debian, explique les alternatives et demande-moi.
4. Détecter début/fin de diffusion (sortie de UxPlay) pour prévenir l'orchestrateur et l'écran (`casting` ↔ `ready`).
5. Service systemd `berrycast-airplay.service` (utilisateur dédié, pas root, redémarrage auto).

Critère de réussite : mon iPhone se recopie sur la TV via le Pi 3, et le code de vérification s'affiche sur la TV la première fois.
