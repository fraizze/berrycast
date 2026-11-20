# spikes/01-p2p — Test de faisabilité n°1 : apparaître dans Windows + K

Prototype **jetable** (étape 02).

| Fichier | Rôle |
|---|---|
| `check.sh` | Diagnostic en lecture seule : OS, puce Wi-Fi, P2P, wpa_supplicant, NetworkManager |
| `p2p_listen.py` | annonce le Pi comme écran Miracast (« BerryCast-Test ») et affiche les événements Wi-Fi Direct ; `sudo python3 p2p_listen.py` |

Les résultats bruts (`check-result*.txt`, `*.log`) restent sur votre PC : ils sont ignorés par Git.
Le rapport final sera dans [`docs/recherche/01-p2p.md`](../../docs/recherche/01-p2p.md).
