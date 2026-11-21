# system/dev/

Services de l'**image de développement** uniquement (`berrycast-dev-*.img.xz`) :

| Service | Rôle | Utilisateur |
|---|---|---|
| `berrycast-devsetup.service` | applique `berrycast-wifi.txt` (Wi-Fi, pays, mot de passe SSH) au démarrage | root (nécessaire) |
| `berrycast-devscreen.service` | écran HDMI « BerryCast dev » : adresse IP, état du Wi-Fi | `berrycast` (tty1 ouvert par systemd : `StandardOutput=tty`) |
| `berrycast-setupui.service` | configuration au clavier sur la TV (texte par défaut, pygame en option) ; démarre seule si le Wi-Fi ne se connecte pas | `berrycast` (clavier et écran = tty1) |
| `berrycast-miracast.service` | Miracast (Windows + K) : Wi-Fi Direct, PIN, RTSP, lecteur GStreamer | `berrycast` (netdev, video, render, audio + capacités réseau) |
| `berrycast-airplay.service` | AirPlay (UxPlay) avec code PIN | `berrycast` (video, render, audio) |
| `berrycast-setup-apply.path` / `.service` | applique les réglages saisis (mot de passe de pi, pays, clavier, Wi-Fi) | root (nécessaire) |

Ils seront remplacés par les vrais services (écran, premier lancement…) aux étapes 05 et 06.
Mode d'emploi : [`docs/image-dev.md`](../../docs/image-dev.md).
