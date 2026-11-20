# Prompt 02 — Test de faisabilité n°1 : apparaître dans Windows + K

Lis CLAUDE.md. C'est un **prototype jetable** : tout va dans `spikes/01-p2p/`.

Objectif : sur mon **Pi 3 Model B** sous **Raspberry Pi OS Lite 64-bit (Trixie, NetworkManager)**, faire apparaître le Pi dans la liste **Windows + K** de mon PC Windows 11.

Étapes attendues :
1. **Diagnostic** (script `check.sh` que je lance en SSH) : version de l'OS, du noyau, de wpa_supplicant ; `iw list` → la puce supporte-t-elle P2P-GO / P2P-client et quelles combinaisons d'interfaces (station + P2P en même temps ?) ; wpa_supplicant est-il lancé avec D-Bus et le support P2P ; NetworkManager gère-t-il le P2P ?
2. Explique-moi les résultats en français simple.
3. Choisis la façon la plus propre d'activer le Wi-Fi Direct **sans casser NetworkManager** (de préférence via l'API **D-Bus de wpa_supplicant** ; documente tes sources).
4. Prototype Python (`p2p_listen.py`) qui :
   - configure le nom d'appareil P2P (« BerryCast-Test »), le type d'appareil « Display »,
   - publie les **éléments d'information Wi-Fi Display (WFD IE)** d'un *sink* (vérifie le format exact dans la spécification Wi-Fi Display / la doc wpa_supplicant),
   - se met en écoute P2P et affiche dans le terminal les événements (découverte, demande de connexion, PIN demandé…).
5. Donne-moi la procédure de test exacte : quoi lancer sur le Pi, quoi faire sur le PC (Windows + K), quoi m'envoyer.

**Critère de réussite** : « BerryCast-Test » apparaît dans Windows + K.
**Attention** : demande-moi avant toute commande qui pourrait couper le Wi-Fi du Pi, et donne-moi la commande pour revenir en arrière. Si la puce ne permet pas station + P2P en même temps, dis-le clairement et propose des options.

Termine par un **rapport** dans `docs/recherche/01-p2p.md` : ce qui marche, ce qui ne marche pas, décisions.
