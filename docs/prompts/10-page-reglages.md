# Prompt 10 — Page de réglages

Lis CLAUDE.md. Code dans `berrycast/web/`.

Objectif : une fois configuré, on peut ouvrir `http://<nom>.local` (et l'adresse IP, affichée sur l'écran `ready`) depuis un téléphone ou un PC du même Wi-Fi.

À faire :
1. Accès protégé : à l'ouverture, un **code à 6 chiffres s'affiche sur la TV** (écran temporaire) et doit être saisi sur la page. Session valable 15 min.
2. Réglages : nom de l'appareil, Wi-Fi (changer de réseau, avec confirmation car on risque de perdre l'accès), langue, sortie audio (HDMI/jack), activer/désactiver AirPlay et Miracast, redémarrer, éteindre proprement, **réinitialiser** (retour au premier lancement).
3. Infos : version de BerryCast, modèle de Pi, température, adresse IP.
4. Même style : fond noir, texte blanc, gros boutons, sans framework.
5. Sécurité de base : pas d'injection de commande (jamais de shell avec des entrées utilisateur), validation de toutes les entrées, protection CSRF simple.

Critère de réussite : je renomme mon Pi depuis mon iPhone et le nouveau nom apparaît dans Windows + K et dans la Recopie de l'écran sans redémarrage manuel.
