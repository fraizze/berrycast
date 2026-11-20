# Prompt 08 — Miracast complet (Windows + K)

Lis CLAUDE.md et tous les rapports `docs/recherche/`. Transforme les prototypes 02-04 en **code propre** dans `berrycast/miracast/`.

À faire :
1. Modules séparés : `p2p.py` (Wi-Fi Direct via D-Bus wpa_supplicant), `rtsp_sink.py` (négociation M1-M16, keep-alive, TEARDOWN), `pipeline.py` (GStreamer, choix du décodeur selon le modèle), `service.py` (assemble le tout).
2. **PIN** : à chaque demande de connexion, générer le PIN, l'afficher en grand via l'écran `pin`, l'effacer une fois connecté ou après expiration.
3. **Mémoriser les PC déjà appairés** (groupes persistants) pour ne pas redemander le PIN à chaque fois, si la puce/wpa_supplicant le permet. Sinon, documente.
4. Coexistence avec le Wi-Fi de la maison (station + P2P) selon ce qu'on a appris à l'étape 02.
5. Robustesse : coupure du PC, perte du Wi-Fi, flux corrompu → retour propre à l'écran `ready` en moins de 5 s, sans redémarrer le service.
6. Nom affiché dans Windows + K = `device_name` de la config.
7. Service systemd `berrycast-miracast.service` avec les permissions D-Bus/polkit minimales.
8. Tests unitaires du parseur RTSP (avec les journaux réels de l'étape 03 comme données de test).

Critère de réussite : depuis Windows 11, Windows + K → le nom → PIN affiché sur la TV → mon écran apparaît sur la TV, 5 connexions/déconnexions d'affilée sans bug.
