# Prompt 05 — L'écran HDMI (fond noir, texte blanc)

Lis CLAUDE.md. Maintenant on écrit le **vrai code** (plus des prototypes), dans `berrycast/display/`.

Objectif : un service qui affiche des messages simples sur l'écran HDMI, **fond noir, texte blanc, gros caractères, centré**. Rien de plus.

À faire :
1. Afficher sur la **console tty1** : masquer le curseur, désactiver la mise en veille de l'écran console, désactiver l'invite de connexion (`getty@tty1`) quand BerryCast est installé, choisir une grande police console (ex. Terminus, taille adaptée à la résolution).
2. Une API simple utilisable par les autres modules : `show(screen_name, **values)`. Écrans à prévoir (textes dans `i18n`) :
   - `welcome_setup` : Bienvenue + Wi-Fi temporaire + mot de passe + adresse de la page + **code de vérification 6 chiffres**
   - `connecting_wifi` : « Connexion au Wi-Fi… »
   - `ready` : nom de l'appareil, « Prêt à recevoir », « PC : Windows + K », « iPhone : Recopie de l'écran », adresse de la page de réglages
   - `pin` : « Code à saisir : 1234 5678 » en très grand + nom de l'appareil qui se connecte
   - `casting` : (rien, la vidéo prend l'écran)
   - `error` : message + « Redémarrage dans X s »
3. Communication avec les autres services : petit socket Unix local ou D-Bus (choisis le plus simple et explique).
4. Quand une diffusion se termine, l'écran doit **revenir** à `ready` (la vidéo kmssink libère l'écran → réafficher la console).
5. Service systemd `berrycast-display.service` (utilisateur dédié, droits minimaux, redémarrage auto).
6. Un outil de démo : `python3 -m berrycast.display.demo` qui fait défiler tous les écrans (pour que je vérifie sur ma TV).

Critère de réussite : sur ma TV, tous les écrans de démo s'affichent proprement, lisibles à 3 mètres.
