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
