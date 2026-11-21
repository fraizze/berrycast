# Rapport 02 — Diffusion Miracast et AirPlay (première version complète)

> Statut : AirPlay : l'iPhone voit le Pi et s'appaire (code OK), image pas encore affichée.
> Miracast : méthode MICE écrite, pas encore essayée sur le Pi.

## Miracast (Windows + K) — `berrycast/miracast/`

### Essai 1 (abandonné) : groupe Wi-Fi Direct, comme lazycast

Le Pi créait un groupe Wi-Fi Direct permanent et acceptait un PIN. **Constaté sur le Pi :**
chaque groupe était supprimé dans la seconde où il était créé (`AP-DISABLED`,
`nl80211: deinit`, sans `P2P-GROUP-REMOVED`). **Cause, vérifiée dans le code source de
NetworkManager 1.52** (`src/core/supplicant/nm-supplicant-interface.c`) : sur le signal
`GroupStarted`, NetworkManager crée un objet pour le groupe ; comme ce n'est pas lui qui l'a
demandé, son appareil Wi-Fi Direct ignore l'évènement et l'objet est détruit, ce qui appelle
`RemoveInterface` sur wpa_supplicant (« NMSupplicantInterface is disposing »). Aucun réglage
ne le désactive (la prise en charge P2P dépend seulement des capacités de wpa_supplicant).
lazycast le signale aussi : « Debian Bookworm seems to cause some issues ».

### Méthode actuelle : Miracast over Infrastructure (MS-MICE)

| Étape | Module | Méthode |
|---|---|---|
| Découverte | `p2p.py` | Écoute Wi-Fi Direct (sans groupe) ; nom, type TV, `WFDIEs`, extension fabricant Microsoft (`P2PDeviceConfig.VendorExtension` : capacité MICE, nom d'hôte, IP) |
| Découverte (réseau) | `mice.py`, `devsetup.py` | mDNS `_display._tcp` port 7250 (fichier avahi, identifiant dérivé de `/etc/machine-id`) |
| Connexion | `mice.py` | Le PC se connecte au port TCP 7250 et envoie `SOURCE_READY` (port RTSP) |
| Négociation | `rtsp_sink.py` | Le Pi se connecte au RTSP du PC ; M1–M7, M16, TEARDOWN |
| Vidéo + son | `pipeline.py` | RTP/MPEG-TS par le Wi-Fi de la maison → H.264 → `kmssink` ; AAC → `alsasink` |

Conditions : **le PC doit être sur le même réseau que le Pi**. Pas de chiffrement ni de code
PIN dans cette version (comme lazycast) : réservé à un réseau de confiance. Méthode reprise de
lazycast (`newmice.py`, `project.py`), spécification [MS-MICE] de Microsoft.

## AirPlay — `berrycast/airplay/service.py`

UxPlay (Debian 13 : 1.71) lancé tel quel : `uxplay -n <nom> -nh -pin <code> -p -vs kmssink
-vsync no -as "alsasink device=…" -bt709` (`-avdec` sur Pi 5), sous `stdbuf -oL`. Code PIN Apple à 4 chiffres, fixe pour
l'appareil. État suivi par les connexions TCP actives (ports fixes de `-p` : 7000 contrôle,
7100 vidéo) ; demande de code détectée par le dessin du code qu'UxPlay affiche.

## Une seule diffusion à la fois

Fichiers d'état `/run/berrycast/{miracast,airplay}.json` (`berrycast/cast_state.py`), lus par
l'écran. Windows diffuse → UxPlay est arrêté (l'iPhone ne voit plus le Pi), puis relancé.
iPhone diffuse → la demande MICE du PC est refusée. Choix : **refuser** (CLAUDE.md, point 6).

## Risques connus (à vérifier sur le Pi)

1. **Écran noir avec `kmssink`** : même famille de problème que l'interface pygame (affichage
   KMS par l'utilisateur `berrycast`). Repli possible : variable `BERRYCAST_VIDEO_SINK`.
2. **Windows peut d'abord tenter le Miracast classique** (demande d'un PIN) : lazycast
   conseille d'annuler et de réessayer ; Windows passe alors par MICE.
3. **UxPlay rejetait toutes les images** (horloges) : corrigé avec `-vsync no` ; messages
   d'UxPlay désormais en direct (`stdbuf -oL`).
4. Le **code iPhone** n'apparaît en grand que si le dessin d'UxPlay est bien reconnu ; il
   reste de toute façon affiché sur l'écran d'accueil.
5. Noms exacts des paquets dans l'image (uxplay, gstreamer1.0-*) : vérifiés pour Debian 13.

## Constats sur le Pi 3 (vidéo)

- **Windows : écran noir.** Le décodeur matériel (`v4l2h264dec`) n'accepte que les profils
  H.264 `baseline`, `constrained-baseline`, `main`, `high` (modèle de son entrée, vu avec
  `gst-inspect-1.0`), pas le `constrained-high` que Windows envoyait. Le Pi n'annonce donc
  que **Constrained Baseline** (profil `01`, obligatoire pour toute source Wi-Fi Display),
  et seulement les modes qui tiennent dans l'écran (lu dans `/sys/class/drm/*/modes`).
  Secours : si Windows choisit quand même un autre profil (lu dans M4), décodage par le
  processeur (`avdec_h264`). (Plus de bascule « après 2 arrêts du lecteur » : un arrêt
  peut venir du son, et le décodage processeur est bien trop lent sur un Pi 3.)
- **Pas d'agrandissement par `kmssink`** (`can-scale=true` → `No space left on device`) :
  `videoscale` met l'image à la taille de l'écran, comme dans la chaîne d'UxPlay
  (`v4l2h264dec ! v4l2convert ! videoscale ! kmssink can-scale=false`).
- **iPhone en paysage** : c'est la *hauteur* demandée par `-s` qui règle la taille ; avec
  1080, l'image en paysage faisait ~2340 de large (plus que l'écran) et le lecteur plantait.
  Le Pi demande `-s 1920x872` (écran 1920x1080) : l'image en paysage tient dans la largeur.
- **Windows : « No valid frames found »** (h264parse ne reçoit que des morceaux d'image
  « différentiels », jamais l'image complète avec ses réglages SPS/PPS). Deux causes
  corrigées : le lecteur (1 à 2 s pour démarrer sur le Pi 3) n'écoutait pas encore quand
  Windows commençait à envoyer (on attend maintenant que le port UDP 1028 soit ouvert
  avant PLAY) ; et le tampon de réception UDP était limité à ~200 Ko
  (`net.core.rmem_max`, porté à 8 Mo par `system/sysctl/90-berrycast.conf`). L'iPhone
  n'a pas ce problème : AirPlay passe par TCP, qui renvoie les morceaux perdus.
- **Windows : ~20 s de retard.** `kmssink can-scale=false` n'accepte que la taille de
  l'écran *et* la forme de pixel qu'il calcule d'après les dimensions physiques de la TV
  (code de kmssink). `videoscale` recalculait donc chaque image 1080p par le processeur :
  trop lent sur le Pi 3, les images s'empilaient. `v4l2convert` (puce ISP) enlève taille
  et forme de pixel de ses contraintes : il produit directement le format de l'écran.
  Chaîne Windows : `v4l2h264dec ! queue leaky ! v4l2convert ! kmssink`. La file
  « leaky » saute des images décodées si l'affichage prend du retard, au lieu de les
  empiler. `gst-launch -v` écrit les formats négociés dans le journal.
- **Image Windows en 1920x988 (bandes noires).** La TV annonce des dimensions physiques
  qui donnent à kmssink des pixels « non carrés » (54/59) ; v4l2convert gardait alors les
  proportions en réduisant la hauteur. Un `capsfilter` impose la taille exacte de l'écran
  (lue dans `/sys/class/drm`) : image plein écran. Résultat mesuré avant ce réglage :
  ~1 s de retard (au lieu de ~20 s).
- **Gros retard et gels en lisant une vidéo sur le PC.** Deux causes : (1) le son change
  de format en pleine diffusion (4000 Hz mono, puis vrai son) et la sortie son plantait
  tout le lecteur → format de sortie fixe (48 kHz stéréo) ; (2) en 1080p, le débit sature
  le Wi-Fi 2,4 GHz du Pi 3 → 720p demandé à Windows sur Pi 3 / Zero 2 W (1080p sur
  Pi 4 / 5), agrandi par la puce. Le journal signale les paquets perdus faute de place
  (`/proc/net/udp`, colonne « drops »).
- **Image floue et étirée.** Le premier champ de `wfd_video_formats` (mode « natif » :
  bits 2-0 = table, bits 7-3 = numéro du mode) valait `00` = 640x480p60 : Windows
  envoyait du 640x480 (4:3), agrandi et étiré en 16:9. On annonce maintenant le meilleur
  mode proposé (`28` = 1280x720p30 sur Pi 3, `38` = 1920x1080p30 sur Pi 4/5). Le mode
  choisi par Windows est écrit au journal (« Mode vidéo choisi par la source »).
