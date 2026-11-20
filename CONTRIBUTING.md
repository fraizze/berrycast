# Contribuer à BerryCast

Merci de votre intérêt ! Quelques règles simples :

- **Petites modifications**, une idée par commit, avec un message clair.
- **Code commenté en français**, noms de variables et de fonctions en anglais.
- **Python 3** et bibliothèque standard autant que possible. En production, uniquement des paquets
  Debian (`python3-*`), pas de `pip`.
- **Pas de secrets** dans le dépôt (mots de passe, clés…).
- Toute contribution est publiée sous licence **GPL-3.0-or-later** (GNU GPL version 3 ou toute version ultérieure).

## Lancer les tests et le linter

Depuis la racine du dépôt :

```sh
python -m venv .venv
# Windows : .venv\Scripts\activate    Linux / macOS : source .venv/bin/activate
pip install pytest ruff
ruff check .
pytest
```

GitHub Actions lance automatiquement les mêmes vérifications à chaque envoi (`push`) et pull request.

## Signaler un problème

Ouvrez une *issue* en précisant : le modèle de Raspberry Pi, l'appareil source
(PC Windows, iPhone…), ce que vous avez fait, et ce qui s'est passé.
