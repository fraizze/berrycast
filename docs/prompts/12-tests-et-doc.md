# Prompt 12 — Tests, documentation, compatibilité

Lis CLAUDE.md.

À faire :
1. Relis tout le code : simplifie, supprime le code mort, vérifie les erreurs non gérées et les problèmes de sécurité. Fais-moi une liste de ce que tu corriges.
2. Tests : couverture correcte des parties testables sans Pi (config, i18n, RTSP, machine à états, validation des entrées web).
3. `docs/compatibilite.md` : matrice modèles × (AirPlay, Miracast, qualité, testé par qui), avec « non testé » pour ce que je n'ai pas pu tester.
4. `docs/depannage.md` : les problèmes courants (n'apparaît pas dans Windows + K, iPhone ne voit pas l'appareil, écran noir, son absent, Wi-Fi qui ne se connecte pas…) avec solutions simples.
5. Modèles d'issues GitHub (bug avec sortie de `berrycast-diag`, demande de fonctionnalité).
6. `CHANGELOG.md` et première version `v0.1.0`.
7. README : captures d'écran (je te les fournirai) + badges (licence, build).

Critère de réussite : quelqu'un qui découvre le dépôt comprend en 1 minute ce que c'est, et sait quoi faire en cas de problème.
