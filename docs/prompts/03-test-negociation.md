# Prompt 03 — Test de faisabilité n°2 : la négociation avec Windows

Lis CLAUDE.md et `docs/recherche/01-p2p.md`. Prototype jetable dans `spikes/02-rtsp/`.

Objectif : quand je choisis « BerryCast-Test » dans Windows + K, la connexion Wi-Fi Direct s'établit (avec PIN si demandé) et la **négociation RTSP Miracast** aboutit : Windows commence à envoyer le flux vidéo.

À faire :
1. Rappelle-moi en 10 lignes comment se déroule une session Miracast côté *sink* : connexion P2P (le Pi en groupe owner ou client), adresse IP, connexion RTSP (port 7236), messages **M1 à M7**, `GET_PARAMETER` keep-alive (M16), TEARDOWN.
2. Étends le prototype : accepter la connexion P2P (méthode PIN : générer un PIN à 8 chiffres et l'**afficher dans le terminal**), obtenir/attribuer les adresses IP sur l'interface P2P, puis implémenter un **sink RTSP minimal** en Python (asyncio, sans dépendance externe).
3. Annonce des capacités prudentes et compatibles : vidéo H.264 *Constrained Baseline/High* jusqu'à 1080p30, audio AAC ou LPCM. Vérifie les formats exacts (`wfd_video_formats`, `wfd_audio_codecs`, `wfd_client_rtp_ports`…) dans la spécification.
4. **Journalise chaque message** RTSP échangé (dans un fichier) : c'est précieux pour déboguer Windows 11.
5. Une fois en PLAY : enregistre le flux RTP reçu (port UDP annoncé) dans un fichier `.ts` pendant 20 secondes, sans le décoder.

**Critère de réussite** : un fichier `.ts` non vide est enregistré pendant que mon PC diffuse.
Si Windows 11 refuse à une étape, analyse les journaux, explique pourquoi et propose une correction. Rapport dans `docs/recherche/02-rtsp.md`.
