# Prompt 06 — Premier lancement + code de vérification

Lis CLAUDE.md. Code dans `berrycast/setup/`.

Objectif : au tout premier démarrage (ou si aucun Wi-Fi connu n'est trouvé après ~2 min), le Pi passe en **mode configuration**.

Parcours utilisateur attendu :
1. La TV affiche l'écran `welcome_setup` : un Wi-Fi temporaire `BerryCast-Setup-XXXX` (XXXX = fin de l'adresse MAC), son mot de passe (aléatoire, lisible, sans caractères ambigus), l'adresse `http://10.42.0.1` (ou équivalent), et un **code de vérification à 6 chiffres** (aléatoire, change à chaque démarrage du mode configuration).
2. Sur le téléphone : je rejoins ce Wi-Fi, j'ouvre l'adresse (bonus : portail captif pour que la page s'ouvre toute seule).
3. **Première page : saisir le code de vérification** affiché sur la TV. 5 essais max, puis blocage 1 min.
4. Ensuite : nom de l'appareil (ex. « TV Salon », vérifie les caractères autorisés pour le nom d'hôte / AirPlay / Wi-Fi Direct et convertis proprement), langue, choix du Wi-Fi de la maison dans la liste des réseaux détectés (+ saisie manuelle) et son mot de passe.
5. Le Pi teste la connexion au Wi-Fi de la maison. Succès → la page affiche « C'est bon ! » avec la nouvelle adresse, la TV passe à `ready`. Échec → retour en mode configuration avec le message d'erreur.

Technique :
- Point d'accès temporaire via **NetworkManager** (mode AP, `ipv4.method shared`). Attention à la puce du Pi 3 : désactiver PMF (`wifi-sec.pmf disable`) sinon les iPhone refusent la connexion (problème déjà rencontré).
- Scanner les Wi-Fi **avant** de passer en mode AP (une seule puce), garder la liste.
- Serveur web : bibliothèque standard Python (`http.server` + JSON) ou très petit framework disponible en paquet Debian. HTML/CSS/JS sans framework, **fond noir texte blanc**, gros boutons, utilisable sur téléphone.
- Appliquer le nom partout : nom d'hôte, avahi, configuration AirPlay et Miracast.
- Sauvegarder dans `config.toml` (`setup_done = true`).

Critère de réussite : avec mon iPhone, je configure le Pi de A à Z sans clavier ni SSH, et il rejoint mon Wi-Fi.
