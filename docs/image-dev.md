# Image de développement BerryCast : mode d'emploi

L'image `berrycast-dev-<date>-<commit>.img.xz` sert à **tester en conditions réelles** pendant le
développement. Elle est reconstruite automatiquement à chaque envoi sur GitHub.

Ce qu'elle contient : Raspberry Pi OS Lite 64 bits (Trixie) + tout le dépôt BerryCast dans
`/opt/berrycast` (y compris les prototypes `spikes/`), utilisateur `pi`, nom d'hôte `berrycast`,
SSH activé, **aucun mot de passe par défaut**.

> ⚠️ Image de développement : SSH est ouvert sur le réseau. Choisissez un vrai mot de passe et
> ne l'utilisez que sur un réseau de confiance.

Il vous faut : la carte microSD, un câble HDMI vers la TV, l'alimentation, et **un clavier USB**
branché au Pi (pour la configuration ; il peut être débranché ensuite).

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

## 3. Premier démarrage : configuration au clavier sur la TV

1. Mettez la carte dans le Pi, branchez le **clavier USB**, le **HDMI**, puis l'**alimentation**.
2. Le premier démarrage prend 1 à 2 minutes (le Pi agrandit sa partition et peut redémarrer une fois).
   La TV affiche d'abord l'écran « BerryCast dev ».
3. Après une vingtaine de secondes sans Wi-Fi, l'écran **« Bienvenue sur BerryCast »** s'affiche.
   Avec le clavier :
   - **↑ ↓** pour passer d'un champ à l'autre, **◀ ▶** (flèches gauche/droite) pour changer un choix,
     **Entrée** pour ouvrir une liste (une lettre saute directement au bon endroit) ;
   - **Clavier** : choisissez d'abord la disposition de votre clavier (ex. *Suisse romand*) ; elle
     s'applique tout de suite ;
   - **Wi-Fi** : choisissez votre réseau dans la liste (ou *Autre réseau* pour taper son nom) ;
     *Actualiser la liste des Wi-Fi* relance la recherche ;
   - **Mot de passe du Wi-Fi**, **Pays** (le pays détecté est proposé en premier ; vide = réglage
     international), **mot de passe de « pi »** (8 caractères minimum, deux fois) ;
   - **Valider**.
4. Le Pi se connecte (jusqu'à une minute), puis affiche **« C'est prêt ! »** avec son adresse IP.
   En cas d'erreur (mauvais mot de passe, Wi-Fi introuvable), le formulaire revient avec le message.
5. **Entrée** (ou 20 secondes) : retour à l'écran « BerryCast dev ».

La configuration ne s'affiche que si le Wi-Fi ne se connecte pas. Pour la **relancer** plus tard :
créez un fichier vide nommé `berrycast-configurer.txt` sur la carte (lecteur **bootfs**, voir § 6),
ou, en SSH : `sudo systemctl start berrycast-setupui`.

## 4. Se connecter en SSH depuis le PC

1. Le PC doit être sur **le même Wi-Fi** que le Pi.
2. Ouvrez **PowerShell** et tapez :

   ```powershell
   ssh pi@berrycast.local
   ```

   ou, si ça ne répond pas, avec l'adresse IP affichée sur la TV (par exemple `192.168.1.20`) :

   ```powershell
   ssh pi@192.168.1.20
   ```

3. La première fois, répondez `yes` à la question sur l'empreinte (« fingerprint »).
4. Tapez le mot de passe de « pi » choisi (rien ne s'affiche pendant la frappe : c'est normal).

**Après avoir flashé une nouvelle image**, SSH affiche « REMOTE HOST IDENTIFICATION HAS CHANGED » :
c'est normal (nouvelle installation = nouvelle empreinte). Effacez l'ancienne empreinte :

```powershell
ssh-keygen -R berrycast.local
```

(et `ssh-keygen -R <adresse IP>` si vous utilisiez l'adresse IP), puis reconnectez-vous.

## 5. En cas de problème

| Ce que montre la TV | Que faire |
|---|---|
| « BerryCast dev » reste affiché, pas de configuration | attendre 2 minutes (un Wi-Fi est peut-être déjà enregistré) ; sinon voir § 6 |
| `Connexion refusée … vérifiez le mot de passe du Wi-Fi` | corriger le mot de passe (attention à la disposition du clavier) |
| `Wi-Fi … introuvable` | box allumée ? Pi 3 : réseau en 2,4 GHz uniquement ; *Actualiser la liste* |
| `ATTENTION : pays Wi-Fi non défini` | choisir le pays (le Wi-Fi marche quand même) |
| les lettres tapées ne sont pas les bonnes | changer le champ **Clavier** (première ligne) |
| écran noir | vérifier le câble HDMI et le brancher **avant** l'alimentation |

Sur le Pi, les journaux utiles :

```
journalctl -u berrycast-setupui -b
journalctl -u berrycast-setup-apply -b
journalctl -u berrycast-devscreen -b
```

## 6. Option avancée de secours : `berrycast-wifi.txt` (sans clavier)

Pour configurer le Wi-Fi sans clavier, depuis le PC, avant le premier démarrage :

1. Après le flash, retirez puis remettez la carte dans le PC : un lecteur **bootfs** apparaît.
2. Ouvrez `berrycast-wifi.txt` avec le **Bloc-notes** et remplissez après le signe `=` :

   ```
   wifi_nom=Nom exact du Wi-Fi
   wifi_mot_de_passe=Mot de passe du Wi-Fi
   pays=CH
   ssh_mot_de_passe=Un mot de passe d'au moins 8 caractères
   ```

3. **Fichier → Enregistrer**, puis clic droit sur **bootfs** → **Éjecter**.

Le Pi lit ce fichier au démarrage, puis **efface les mots de passe** et écrit un compte rendu en haut.
Le Wi-Fi se connectant, la configuration au clavier ne s'affiche pas.

**Le champ `pays`** : code à 2 lettres (norme **ISO 3166**, majuscules ou minuscules), par exemple
`CH` Suisse, `FR` France, `BE` Belgique, `CA` Canada, `US` États-Unis, `DE` Allemagne. Liste complète :
<https://fr.wikipedia.org/wiki/ISO_3166-1_alpha-2>. Vide ou inconnu : réglage Wi-Fi international
(rien n'est bloqué) et avertissement sur la TV.

**Partage de connexion d'un iPhone** : `wifi_nom` = nom de l'iPhone (Réglages → Général →
Informations → Nom) ; activez **Maximiser la compatibilité** (2,4 GHz, seule bande du Pi 3 B).
