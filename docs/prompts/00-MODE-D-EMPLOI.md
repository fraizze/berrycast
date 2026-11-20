# Mode d'emploi des prompts BerryCast

## Avant de commencer
1. Crée un dépôt GitHub vide (ex. `berrycast`) et clone-le sur ton PC.
2. Copie le fichier **CLAUDE.md** et le dossier **.claude** à la racine du dépôt (Claude Code les lit tout seuls). Le dossier .claude bloque tout envoi sur GitHub sans ta validation.
3. Ouvre Claude Code dans le dossier du dépôt.
4. Garde ton Pi 3 branché (HDMI + alimentation), connecté en SSH depuis ton PC.

## Comment utiliser les prompts
- Donne-les **dans l'ordre**, **un seul à la fois** : copie tout le contenu du fichier (sauf le titre) et colle-le dans Claude Code.
- À la fin de chaque étape, **teste sur le Pi** avec les commandes que Claude Code te donne.
- Si ça marche → fais un commit (`git add . && git commit -m "..."` ou demande à Claude Code de le faire) → passe au prompt suivant.
- Si ça ne marche pas → colle l'erreur dans Claude Code et demande-lui de corriger **avant** de passer à la suite.

## Les étapes
| # | Fichier | Ce que ça fait | Durée estimée |
|---|---|---|---|
| 01 | 01-squelette.md | Crée la base du dépôt GitHub | court |
| 02 | 02-test-wifi-direct.md | **Test de faisabilité** : le Pi apparaît-il dans Windows + K ? | moyen |
| 03 | 03-test-negociation.md | **Test de faisabilité** : Windows accepte-t-il de diffuser vers le Pi ? | long |
| 04 | 04-test-video.md | **Test de faisabilité** : le Pi affiche-t-il la vidéo de façon fluide ? | moyen |
| ⛔ | — | **STOP** : si un test 02-04 échoue, on fait le point avant d'aller plus loin | — |
| 05 | 05-ecran-hdmi.md | Écran fond noir / texte blanc | court |
| 06 | 06-premier-lancement.md | Configuration au premier démarrage + code de vérification | long |
| 07 | 07-airplay.md | Recopie de l'écran iPhone (UxPlay) + code affiché | moyen |
| 08 | 08-miracast.md | Windows + K complet + PIN affiché | long |
| 09 | 09-orchestrateur.md | Chef d'orchestre : une diffusion à la fois, retours d'erreur | moyen |
| 10 | 10-page-reglages.md | Page de réglages (nom, Wi-Fi, audio…) | moyen |
| 11 | 11-image-flashable.md | Image `.img.xz` à flasher avec balenaEtcher, publiée sur GitHub | long |
| 12 | 12-tests-et-doc.md | Tests, documentation, compatibilité des modèles | moyen |

Les étapes 02 à 04 sont les plus risquées : elles vérifient que Miracast est possible sur la dernière version de Raspberry Pi OS. Si l'une échoue, reviens me voir (Claude dans le chat) avec le rapport.
