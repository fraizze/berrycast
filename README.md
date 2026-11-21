# BerryCast

**Français** · [English](README.en.md)

> **Statut : en développement.** BerryCast n'est pas encore utilisable.
> Aucune image n'est disponible pour l'instant dans les *Releases*.

BerryCast transforme un **Raspberry Pi** branché en HDMI sur une TV ou un écran en **écran sans fil** :

- depuis un **PC Windows 10 ou 11** : appuyez sur **Windows + K** (« Diffuser ») et choisissez votre BerryCast ;
- depuis un **iPhone, iPad ou Mac** : utilisez **« Recopie de l'écran »** et choisissez votre BerryCast.

Rien à installer sur le PC, l'iPhone ou le Mac. Aucune ligne de commande à taper.

## Modèles de Raspberry Pi compatibles

Seuls les modèles avec **Wi-Fi intégré** sont compatibles.

| Priorité | Modèles | Image |
|---|---|---|
| 1 (test principal) | Raspberry Pi 3 Model B | arm64 |
| 1 | Pi 3 A+, 3 B+, 4 B, 5, Zero 2 W | arm64 |
| 2 (plus tard, « best effort ») | Pi Zero W | armhf 32 bits |

Non compatibles : Pi 1, Pi 2, Pi Zero sans « W » (pas de Wi-Fi).

## Installation

Il vous faut : un Raspberry Pi compatible, une carte **microSD** (8 Go ou plus), un câble HDMI,
l'alimentation du Pi, et un ordinateur pour préparer la carte.

1. **Téléchargez l'image** : ouvrez la page [*Releases*](https://github.com/fraizze/berrycast/releases)
   et téléchargez le fichier `.img.xz` le plus récent. Inutile de le décompresser.
2. **Installez balenaEtcher** depuis [etcher.balena.io](https://etcher.balena.io/) (gratuit, Windows / Mac / Linux).
3. **Flashez la carte** :
   - insérez la microSD dans votre ordinateur ;
   - ouvrez balenaEtcher ;
   - cliquez sur **« Flash from file »** et choisissez le fichier `.img.xz` téléchargé ;
   - cliquez sur **« Select target »** et choisissez votre carte microSD (attention à ne pas choisir un autre disque : il serait effacé) ;
   - cliquez sur **« Flash! »** et attendez la fin.
4. **Branchez le Pi** : mettez la microSD dans le Pi, branchez-le en HDMI sur la TV, puis branchez l'alimentation.
5. **Suivez les instructions affichées sur la TV** : au premier démarrage, l'écran vous indique un Wi-Fi
   temporaire à rejoindre avec votre téléphone, puis une page où choisir le nom de l'appareil
   (par exemple « TV Salon ») et le Wi-Fi de la maison.

C'est prêt : votre BerryCast apparaît dans Windows + K et dans la recopie de l'écran de l'iPhone.

## Limites connues

- **Pas de contenus protégés (HDCP)** : Netflix, Disney+, certains lecteurs Blu-ray, etc.
  afficheront un écran noir. C'est une limite volontaire, qui ne sera pas contournée.
- **Une seule diffusion à la fois** : si quelqu'un diffuse déjà, il faut attendre qu'il arrête.

## Remerciements

La partie Miracast s'inspire de [lazycast](https://github.com/homeworkc/lazycast)
(Hsun-Wei Cho, GPL-3.0). La partie AirPlay utilise [UxPlay](https://github.com/FDH2/UxPlay) (GPL-3.0).

## Licence

BerryCast est un logiciel libre, distribué sous licence **GNU GPL version 3 ou toute version ultérieure**
(`GPL-3.0-or-later`, voir [LICENSE](LICENSE)).

Envie d'aider ? Lisez [CONTRIBUTING.md](CONTRIBUTING.md).
