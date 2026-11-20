# CLAUDE.md — Contexte du projet BerryCast

> Ce fichier est lu automatiquement par Claude Code à chaque session.
> « BerryCast » est un **nom de travail** : on pourra le remplacer partout plus tard.

## But du projet
Transformer un Raspberry Pi **avec Wi-Fi intégré** en **écran sans fil** branché en HDMI sur une TV ou un écran, qui accepte **nativement** :
- **Windows + K / « Diffuser »** (Miracast / Wi-Fi Display) depuis un PC Windows 10/11, **sans rien installer sur le PC** ;
- **« Recopie de l'écran »** (AirPlay) depuis un iPhone / iPad / Mac, **sans rien installer**.

Le projet est **open source sur GitHub**. L'utilisateur final télécharge une **image prête à flasher** (`.img.xz`) depuis les *Releases* GitHub, la flashe sur une microSD avec **balenaEtcher**, branche le Pi : ça marche.

## Public visé
Des gens **pas techniques**. Aucune ligne de commande ne doit être nécessaire pour l'utilisateur final. Tout se règle depuis l'écran HDMI + une petite page web sur téléphone.

## Matériel supporté (uniquement les modèles avec Wi-Fi intégré)
| Priorité | Modèles | Image |
|---|---|---|
| 1 (test principal) | Raspberry Pi 3 Model B | arm64 |
| 1 | Pi 3 A+, 3 B+, 4 B, 5, Zero 2 W | arm64 |
| 2 (plus tard, « best effort ») | Pi Zero W | armhf 32 bits |

Pas de Pi 1 / Pi 2 / Zero sans W (pas de Wi-Fi).
Le développeur teste sur un **Raspberry Pi 3 Model B** + un **PC Windows 11** + un **iPhone**.

## Système cible
- **Raspberry Pi OS Lite (64-bit), dernière version** (Debian 13 « Trixie » au moment de l'écriture), **sans bureau**.
- Réseau géré par **NetworkManager** (par défaut sur Raspberry Pi OS). Ne pas installer dhcpcd / ifupdown en parallèle.
- Affichage **sans serveur graphique** : console texte (tty1) pour l'interface, et **KMS/DRM** (`kmssink`) pour la vidéo.

## Choix techniques (validés)
- **Langage principal : Python 3** (bibliothèque standard autant que possible + paquets Debian `python3-*`, pas de pip en production).
- **Vidéo / audio : GStreamer** (paquets Debian). Décodage matériel H.264 via `v4l2h264dec` quand le modèle le permet (Pi 3/4/Zero 2 W), décodage logiciel `avdec_h264` sur Pi 5 (pas de décodeur H.264 matériel).
- **AirPlay : UxPlay** (paquet Debian `uxplay`), utilisé **tel quel** comme brique : on ne le réécrit pas, on le lance et on le configure.
- **Miracast : code maison** (le cœur du projet) : Wi-Fi P2P (Wi-Fi Direct) via **wpa_supplicant (API D-Bus)**, éléments WFD, négociation **RTSP** côté *sink* (messages M1 à M7 + keep-alive + TEARDOWN), réception **RTP / MPEG-TS** → GStreamer.
  - Référence d'inspiration (ancienne, ne marche plus sur les OS récents) : https://github.com/homeworkc/lazycast — on peut s'en inspirer, en respectant sa licence et en le créditant.
- **Services : systemd** (un service par composant + un orchestrateur).
- **Licence : GPL-3.0-or-later** (GNU GPL version 3 ou toute version ultérieure ; compatible avec UxPlay et lazycast).
- **Image flashable** : construite avec l'outil officiel Raspberry Pi (**rpi-image-gen** ou **pi-gen** — vérifier lequel est recommandé actuellement), dans **GitHub Actions**, publiée dans les *Releases*.

## Interface (règle de design : SIMPLE)
- **Fond noir, texte blanc**, gros caractères, centré. Pas de logo, pas d'animation, pas de framework graphique.
- Implémentation préférée : écrire directement sur la **console tty1** avec une grande police console (ex. Terminus via `setfont`). Si ce n'est vraiment pas possible proprement, alternative : `pygame` en mode `kmsdrm`. Demander avant de changer d'approche.
- Langues : **français par défaut**, anglais disponible (fichiers de traduction simples).
- La page web de réglage : HTML/CSS/JS **sans framework**, fond noir texte blanc aussi, utilisable sur téléphone.

## Fonctionnalités demandées
1. **Nom personnalisable** : un seul nom (ex. « TV Salon ») utilisé partout : nom affiché dans Windows + K, dans la liste AirPlay de l'iPhone, nom d'hôte (`tv-salon.local`), écran d'accueil.
2. **Premier lancement** : une petite interface de configuration.
   - L'écran HDMI affiche : « Bienvenue », un Wi-Fi temporaire à rejoindre (`BerryCast-Setup-XXXX` + mot de passe affiché), l'adresse de la page de réglage, et un **code de vérification à 6 chiffres**.
   - Sur le téléphone, la page demande d'abord le **code de vérification** (preuve qu'on voit l'écran), puis : nom de l'appareil, réseau Wi-Fi de la maison (liste des réseaux détectés + mot de passe), langue.
   - Ensuite le Pi rejoint le Wi-Fi de la maison et passe en mode normal.
3. **Écran d'accueil (mode normal)** sur HDMI, fond noir texte blanc : nom de l'appareil, « Prêt à recevoir », comment se connecter (Windows + K / Recopie de l'écran), adresse de la page de réglage.
4. **Code de vérification à la connexion** :
   - Miracast : Windows demande un **code PIN** → le PIN est **affiché en grand sur l'écran HDMI** au moment de la connexion.
   - AirPlay : utiliser l'appairage par code d'UxPlay (option `-pin` si disponible dans la version installée) → code affiché en grand sur l'écran HDMI.
5. **Page de réglages** (accessible ensuite sur le réseau de la maison) : changer le nom, le Wi-Fi, la langue, la sortie audio (HDMI par défaut / jack), activer/désactiver AirPlay ou Miracast, redémarrer. Accès protégé par un **code affiché sur l'écran HDMI** à chaque ouverture.
6. **Une seule diffusion à la fois.** Si quelqu'un diffuse déjà, une autre demande est refusée proprement (ou remplace la première : à décider, demander au développeur).
7. **Retour au mode configuration** si aucun Wi-Fi connu n'est trouvé au démarrage (après ~2 min), pour ne jamais rester bloqué.

## Contraintes importantes
- Le Pi n'a **qu'une puce Wi-Fi**. Elle doit gérer : connexion au Wi-Fi de la maison (pour AirPlay et la page de réglages) **+** Wi-Fi Direct pour Miracast. Vérifier la concurrence station + P2P sur la puce (brcmfmac) ; si c'est impossible, le signaler **avant** de continuer.
- Pas de contenus protégés HDCP (Netflix, etc.) : c'est une limite connue, à documenter, pas à contourner.
- Rien ne doit tourner en root sans nécessité. Les services utilisent un utilisateur dédié (`berrycast`) + les capacités/permissions minimales (groupes `video`, `render`, `audio`, règles polkit/D-Bus pour NetworkManager et wpa_supplicant).
- Robustesse : tout service doit redémarrer seul en cas de crash ; l'écran ne doit jamais rester noir sans message.
- Pas d'accès Internet requis en fonctionnement.

## Organisation du dépôt (cible)
```
berrycast/
├── README.md / README.en.md      # utilisateur final : télécharger, flasher (balenaEtcher), brancher
├── LICENSE                       # GPL-3.0-or-later
├── CLAUDE.md
├── docs/                         # architecture, dépannage, matrice de compatibilité, notes de recherche
├── berrycast/                    # code Python (paquet)
│   ├── config.py                 # lecture/écriture /etc/berrycast/config.toml
│   ├── display/                  # écran HDMI tty1 (fond noir, texte blanc)
│   ├── setup/                    # mode premier lancement (AP temporaire + serveur web)
│   ├── web/                      # page de réglages (HTML/CSS/JS sans framework)
│   ├── airplay/                  # pilotage d'UxPlay
│   ├── miracast/                 # P2P, RTSP sink, pipeline GStreamer
│   ├── orchestrator.py           # machine à états : setup / prêt / diffusion
│   └── i18n/                     # fr.json, en.json
├── system/                       # unités systemd, polkit, udev, config NetworkManager
├── image/                        # configuration de construction de l'image flashable
├── scripts/                      # install.sh (installation sur un Pi existant), outils de dev
├── spikes/                       # prototypes jetables des tests de faisabilité
└── tests/                        # tests unitaires (pytest)
```

## Image de développement (tests en conditions réelles)
- Chaque envoi sur `main` reconstruit l'image `berrycast-dev-<date>-<commit>.img.xz` (pi-gen, GitHub Actions, pré-version « dev » des Releases). Le développeur la flashe avec balenaEtcher et teste.
- Le dépôt est installé dans `/opt/berrycast` sur le Pi ; utilisateur `pi`, hôte `berrycast.local`, Wi-Fi et mot de passe SSH lus dans `berrycast-wifi.txt` (partition de démarrage).
- Détails : `image/README.md` et `docs/image-dev.md`. Les commandes de test données au développeur supposent cette image.

## Règle GitHub (OBLIGATOIRE)
- **Ne JAMAIS envoyer quoi que ce soit sur GitHub sans validation explicite du développeur** : pas de `git push`, pas de création de tag/release, pas de pull request, pas de commande `gh` qui modifie le dépôt distant.
- Avant chaque envoi, présente un **récapitulatif** : liste des commits (titre + fichiers modifiés), branche visée, et pose la question : « Je peux envoyer sur GitHub ? (oui/non) ».
- N'envoie que si la réponse est un **« oui » clair** dans le message qui suit. Un « oui » ne vaut que pour cet envoi-là, pas pour les suivants.
- Les commits **locaux** sont autorisés, mais annonce-les.
- Ne jamais utiliser `git push --force`.

## Méthode de travail (à respecter)
- **Petites étapes.** Une étape = un prompt du développeur. À la fin de chaque étape : résumé de ce qui a été fait, ce qui reste, et **commandes exactes** pour tester sur le Pi.
- Le développeur est **débutant** : explique en français simple, donne des commandes à copier-coller une par une.
- Le Pi est joignable en SSH (`ssh pi@<adresse>`). Tu peux proposer des commandes à exécuter sur le Pi ; **demande avant** de lancer quoi que ce soit qui modifie le réseau du Pi (risque de perdre la connexion SSH) et prévois toujours un moyen de revenir en arrière.
- Ne pas inventer d'API : vérifier la documentation (wpa_supplicant D-Bus, spécification Wi-Fi Display, options d'UxPlay, GStreamer) avant d'écrire le code. Si quelque chose est incertain, faire d'abord un petit prototype dans `spikes/`.
- Commits petits et clairs (en français ou anglais, mais cohérents). Ne jamais committer de secrets.
- Code commenté en français, noms de variables/fonctions en anglais.
