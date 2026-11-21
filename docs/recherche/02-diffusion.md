# Rapport 02 — Diffusion Miracast et AirPlay (première version complète)

> Statut : **écrit et testé sur PC uniquement** (165 tests). Pas encore essayé sur le Pi.

## Miracast (Windows + K) — `berrycast/miracast/`

| Étape | Module | Méthode |
|---|---|---|
| Annonce Wi-Fi Direct | `p2p.py` | D-Bus wpa_supplicant : `P2PDeviceConfig` (nom, type TV), `WFDIEs` |
| Groupe Wi-Fi Direct | `p2p.py` | `P2PDevice.GroupAdd({"persistent": true, "frequency": <canal de la box>})` : le Pi est chef de groupe permanent |
| Code PIN | `p2p.py`, `wfd.py` | `WPS.Start({"Type": "pin", "Pin": …})` sur le groupe = « n'importe quel PC avec ce PIN » (`wpa_supplicant_ap_wps_pin`) |
| Adresse + DHCP | `service.py` | `ip addr replace 192.168.173.1/24`, `dnsmasq` (DHCP seul, une adresse : 192.168.173.80) |
| Négociation | `rtsp_sink.py` | Le Pi se connecte au port RTSP 7236 du PC ; M1–M7, M16, TEARDOWN, traités selon leur type |
| Vidéo + son | `pipeline.py` | `gst-launch-1.0` : RTP → MPEG-TS → H.264 (`v4l2h264dec`, ou `avdec_h264` sur Pi 5) → `kmssink` ; AAC → `alsasink` |

Méthode et valeurs (éléments WFD, formats vidéo) reprises de
[lazycast](https://github.com/homeworkc/lazycast) (Hsun-Wei Cho, GPL-3.0), testé avec Windows,
et vérifiées dans le code source de wpa_supplicant 2.10/2.11 (paquet Debian `wpa`).
Différences : D-Bus au lieu de `wpa_cli`, PIN aléatoire (au lieu d'un PIN fixe), son AAC décodé
par GStreamer, NetworkManager conservé (les interfaces `p2p-wlan0-*` lui sont retirées par
`/etc/NetworkManager/conf.d/berrycast-p2p.conf`).

## AirPlay — `berrycast/airplay/service.py`

UxPlay (Debian 13 : 1.71) lancé tel quel : `uxplay -n <nom> -nh -pin <code> -p -vs kmssink
-as "alsasink device=…" -bt709` (`-avdec` sur Pi 5). Code PIN Apple à 4 chiffres, fixe pour
l'appareil. État suivi par les connexions TCP actives (ports fixes de `-p` : 7000 contrôle,
7100 vidéo) ; demande de code détectée par le dessin du code qu'UxPlay affiche.

## Une seule diffusion à la fois

Fichiers d'état `/run/berrycast/{miracast,airplay}.json` (`berrycast/cast_state.py`), lus par
l'écran. Windows diffuse → UxPlay est arrêté (l'iPhone ne voit plus le Pi), puis relancé.
iPhone diffuse → la connexion du PC est refusée. Choix : **refuser** (CLAUDE.md, point 6).

## Risques connus (à vérifier sur le Pi)

1. **Écran noir avec `kmssink`** : même famille de problème que l'interface pygame (affichage
   KMS par l'utilisateur `berrycast`). Repli possible : variable `BERRYCAST_VIDEO_SINK`.
2. **dnsmasq sans root** (avec les capacités réseau du service) : à confirmer.
3. **Wi-Fi de la maison + groupe Wi-Fi Direct** en même temps sur la puce du Pi 3 : annoncé
   possible (`iw list`), groupe placé sur le canal de la box ; à confirmer en vrai.
4. Le **code iPhone** n'apparaît en grand que si le dessin d'UxPlay est bien reconnu ; il
   reste de toute façon affiché sur l'écran d'accueil.
5. Noms exacts des paquets dans l'image (uxplay, gstreamer1.0-*) : vérifiés pour Debian 13.
