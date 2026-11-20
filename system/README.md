# system/

Fichiers d'intégration au système Raspberry Pi OS (à venir) :

- unités **systemd** (un service par composant + un orchestrateur, redémarrage automatique) ;
- règles **polkit** / **D-Bus** pour piloter NetworkManager et wpa_supplicant sans être root ;
- règles **udev** si besoin ;
- configuration **NetworkManager**.

Les services tournent sous l'utilisateur dédié `berrycast`, avec les droits minimaux.
