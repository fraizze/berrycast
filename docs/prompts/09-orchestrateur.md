# Prompt 09 — Le chef d'orchestre

Lis CLAUDE.md. Code dans `berrycast/orchestrator.py`.

Objectif : un service central qui coordonne tout avec une **machine à états** claire :
`demarrage → (setup | connexion_wifi) → pret → pin_affiche → diffusion → pret` (+ `erreur`).

À faire :
1. Démarre/arrête/surveille les services display, setup, airplay, miracast selon l'état et la config (ex. AirPlay désactivé dans les réglages → service arrêté).
2. **Une seule diffusion à la fois** : si une diffusion est en cours et qu'une autre arrive, propose-moi les deux options (refuser / remplacer) avec leurs avantages, puis implémente celle que je choisis.
3. Retour au mode configuration si aucun Wi-Fi connu n'est disponible après ~2 min au démarrage.
4. Surveillance : si un service plante en boucle, afficher l'écran `error` puis redémarrer proprement.
5. Journaux lisibles (`journalctl -u berrycast-*`), avec une commande de diagnostic `berrycast-diag` qui résume l'état (versions, Wi-Fi, services, température) — utile pour les issues GitHub.
6. Diagramme de la machine à états dans `docs/architecture.md` (Mermaid).

Critère de réussite : je débranche/rebranche le Pi 10 fois, j'alterne iPhone et PC, et l'écran est toujours cohérent.
