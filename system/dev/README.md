# system/dev/

Services de l'**image de développement** uniquement (`berrycast-dev-*.img.xz`) :

| Service | Rôle | Utilisateur |
|---|---|---|
| `berrycast-devsetup.service` | applique `berrycast-wifi.txt` (Wi-Fi, pays, mot de passe SSH) au démarrage | root (nécessaire) |
| `berrycast-devscreen.service` | écran HDMI « BerryCast dev » : adresse IP, état du Wi-Fi | `berrycast` (tty1 ouvert par systemd : `StandardOutput=tty`) |
| `berrycast-setupui.service` | configuration sur la TV au clavier (pygame) ; lancé à la main pour l'instant | `berrycast` (groupes video, render ; clavier = tty1) |

Ils seront remplacés par les vrais services (écran, premier lancement…) aux étapes 05 et 06.
