# Image de développement BerryCast : mode d'emploi

L'image `berrycast-dev-<date>-<commit>.img.xz` sert à **tester en conditions réelles** pendant le
développement. Elle est reconstruite automatiquement à chaque envoi sur GitHub.

Ce qu'elle contient : Raspberry Pi OS Lite 64 bits (Trixie) + tout le dépôt BerryCast dans
`/opt/berrycast` (y compris les prototypes `spikes/`), utilisateur `pi`, nom d'hôte `berrycast`,
SSH activé, **aucun mot de passe par défaut**.

> ⚠️ Image de développement : SSH est ouvert sur le réseau. Choisissez un vrai mot de passe et
> ne l'utilisez que sur un réseau de confiance (par exemple le partage de connexion de votre iPhone).

## 1. Télécharger l'image

1. Ouvrez <https://github.com/fraizze/berrycast/releases/tag/dev>.
2. Dans **Assets**, cliquez sur le fichier `berrycast-dev-….img.xz`. Inutile de le décompresser.

## 2. Flasher la carte microSD avec balenaEtcher

1. Insérez la microSD dans le PC et ouvrez **balenaEtcher**.
2. **Flash from file** → choisissez le fichier `.img.xz` téléchargé.
3. **Select target** → cochez votre carte microSD (vérifiez la taille : ne choisissez pas un autre disque).
4. **Flash!** et attendez la fin (écriture puis vérification).
5. Si Windows affiche « Vous devez formater le disque… » : cliquez sur **Annuler**. Ne formatez **jamais**
   (c'est la partition Linux, que Windows ne sait pas lire).

## 3. Remplir `berrycast-wifi.txt`

1. Retirez puis remettez la carte dans le PC. Un lecteur nommé **bootfs** apparaît dans l'Explorateur.
2. Ouvrez `berrycast-wifi.txt` avec le **Bloc-notes** (clic droit → Ouvrir avec → Bloc-notes).
3. Remplissez les lignes après le signe `=` (sans guillemets) :

   ```
   wifi_nom=Nom exact du partage de connexion
   wifi_mot_de_passe=Mot de passe du partage de connexion
   pays=FR
   ssh_mot_de_passe=Un mot de passe d'au moins 8 caractères
   ```

4. **Fichier → Enregistrer**, puis dans l'Explorateur : clic droit sur **bootfs** → **Éjecter**.

**Avec le partage de connexion d'un iPhone :**

- `wifi_nom` = le **nom de l'iPhone** (Réglages → Général → Informations → Nom), en respectant les
  majuscules. Les apostrophes (’ ou ') sont reconnues dans les deux cas.
- `wifi_mot_de_passe` = Réglages → **Partage de connexion** → Mot de passe du Wi-Fi.
- Dans Réglages → Partage de connexion, activez **Maximiser la compatibilité** : le partage passe
  en 2,4 GHz, la seule bande que le Raspberry Pi 3 Model B connaît.

Une fois le fichier lu, le Raspberry Pi **efface les mots de passe** du fichier et écrit un compte
rendu en haut (« Lu par le Raspberry Pi le… »). Pour changer de Wi-Fi ou de mot de passe SSH plus
tard : remettez la carte dans le PC et remplissez de nouveau le fichier.

## 4. Démarrer le Raspberry Pi

1. Sur l'iPhone : ouvrez Réglages → **Partage de connexion**, activez **Autoriser d'autres
   utilisateurs** et **restez sur cet écran** (sinon l'iPhone cache son réseau).
2. Mettez la carte dans le Pi, branchez le **HDMI**, puis l'**alimentation**.
3. Le premier démarrage prend 1 à 2 minutes (le Pi agrandit sa partition et peut redémarrer une fois).
4. L'écran affiche, en blanc sur fond noir : **BerryCast dev**, l'état du Wi-Fi et l'**adresse IP**.

## 5. Se connecter en SSH depuis le PC

1. Connectez le PC au **même partage de connexion** que le Pi.
2. Ouvrez **PowerShell** et tapez (une seule de ces deux commandes) :

   ```powershell
   ssh pi@berrycast.local
   ```

   ou, si ça ne répond pas, avec l'adresse IP affichée sur la TV (par exemple `172.20.10.3`) :

   ```powershell
   ssh pi@172.20.10.3
   ```

3. La première fois, répondez `yes` à la question sur l'empreinte (« fingerprint »).
4. Tapez le `ssh_mot_de_passe` choisi (rien ne s'affiche pendant la frappe : c'est normal).

**Après avoir flashé une nouvelle image**, SSH affiche « REMOTE HOST IDENTIFICATION HAS CHANGED » :
c'est normal (nouvelle installation = nouvelle empreinte). Effacez l'ancienne empreinte :

```powershell
ssh-keygen -R berrycast.local
```

(et `ssh-keygen -R 172.20.10.3` si vous utilisiez l'adresse IP), puis reconnectez-vous.

## En cas de problème

| Ce que montre la TV | Que faire |
|---|---|
| `Wi-Fi : indisponible (pays non réglé ?)` | vérifier la ligne `pays=` (2 lettres) |
| `Wi-Fi : non connecté` | partage de connexion actif ? même nom exact ? « Maximiser la compatibilité » activé ? |
| `ERREUR : …` | le message dit quelle ligne corriger ; il est aussi écrit en haut de `berrycast-wifi.txt` |
| `ATTENTION : mot de passe SSH non défini` | remplir `ssh_mot_de_passe` (8 caractères minimum) |
| écran noir | vérifier le câble HDMI et le brancher **avant** l'alimentation |

Sur le Pi, les journaux utiles :

```
journalctl -u berrycast-devsetup -b
journalctl -u berrycast-devscreen -b
```
