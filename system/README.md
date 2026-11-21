# system/

Fichiers d'intégration au système Raspberry Pi OS (à venir) :

- unités **systemd** (un service par composant + un orchestrateur, redémarrage automatique) ;
- règles **polkit** / **D-Bus** pour piloter NetworkManager et wpa_supplicant sans être root ;
- règles **udev** si besoin ;
- configuration **NetworkManager**.

Les services tournent sous l'utilisateur dédié `berrycast`, avec les droits minimaux.

## Réglages système installés

- `sysctl/90-berrycast.conf` → `/etc/sysctl.d/` : tampon de réception UDP plus grand
  (vidéo Miracast).
- `networkmanager/berrycast-wifi-powersave.conf` → `/etc/NetworkManager/conf.d/` :
  économie d'énergie du Wi-Fi désactivée (sinon pertes de paquets vidéo : petits gels).
  Retour en arrière : supprimer le fichier puis `sudo iw dev wlan0 set power_save on`.
