# Tester la diffusion : Windows + K (Miracast) et iPhone (AirPlay)

Prérequis : un Pi configuré (Wi-Fi de la maison connecté), avec une image ou une mise à jour
qui contient les services `berrycast-miracast` et `berrycast-airplay`.

## Ce que doit montrer la TV

L'écran « BerryCast dev » affiche maintenant, en plus de l'adresse IP :

```
PC Windows (même Wi-Fi) : Windows + K, puis « BerryCast »
iPhone / iPad / Mac : « Recopie de l'écran », puis « BerryCast »
   code (1re fois) : 4821
```

- Windows : pas de code (Miracast over Infrastructure) ; **le PC doit être sur le même Wi-Fi**.
- Le **code iPhone** (4 chiffres) est fixe pour ce Pi ; l'iPhone ne le demande qu'une fois.
- Quand un appareil demande un code, la TV l'affiche **en très grand**.
- Pendant une diffusion, la vidéo occupe tout l'écran.

## Test 1 : PC Windows

1. Le PC doit être sur **le même Wi-Fi** que le Pi (la box de la maison).
2. Sur le PC : **Windows + K**, puis cliquez sur le nom du Pi.
   Si Windows demande un code PIN : **Annuler**, puis recliquer sur le nom (Windows essaie
   parfois d'abord l'ancienne méthode).
3. L'écran du PC doit apparaître sur la TV après quelques secondes, avec le son.
4. Pour arrêter : Windows + K → **Déconnecter**. La TV revient à l'écran d'accueil.

## Test 2 : iPhone

1. L'iPhone doit être sur **le même Wi-Fi** que le Pi (la box de la maison).
2. Centre de contrôle → **Recopie de l'écran** → le nom du Pi.
3. La première fois : tapez le **code iPhone** affiché en grand sur la TV.
4. L'écran de l'iPhone apparaît sur la TV, avec le son.
5. Pour arrêter : Centre de contrôle → Recopie de l'écran → **Arrêter la recopie**.

## Test 3 : une seule diffusion à la fois

Pendant qu'un appareil diffuse, l'autre ne doit pas pouvoir prendre la main (le PC affiche
une erreur ; le Pi disparaît de la liste de l'iPhone). Quand la première diffusion s'arrête,
tout redevient disponible.

## Journaux à me renvoyer en cas de problème

🖥️ **PC — PowerShell** (mot de passe de « pi ») :

```powershell
ssh pi@berrycast.local "journalctl -u berrycast-miracast -u berrycast-airplay -b --no-pager | tail -150"
```

Le journal Miracast contient tous les messages échangés avec Windows (`<<< envoi`, `>>> reçu`).

## Commandes utiles sur le Pi (🍓 session SSH)

```
systemctl status berrycast-miracast berrycast-airplay --no-pager
sudo systemctl restart berrycast-miracast
sudo systemctl restart berrycast-airplay
cat /run/berrycast/miracast.json /run/berrycast/airplay.json
```
