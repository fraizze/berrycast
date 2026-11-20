"""Faut-il lancer la configuration au démarrage ? (ExecCondition du service setup)

Règle :
- si le Wi-Fi se connecte dans le délai -> NON (le Pi est déjà configuré, ou
  berrycast-wifi.txt a été rempli) ;
- sinon -> OUI : la configuration au clavier s'affiche sur la TV.
Délai : 20 s si aucun Wi-Fi n'est connu (premier démarrage), 120 s si un Wi-Fi est
enregistré (il est peut-être juste lent à répondre, ou la box redémarre).

Pour forcer la configuration : créer le fichier « berrycast-configurer.txt » (vide) sur
la partition de démarrage (visible dans l'Explorateur Windows). Il est effacé ensuite.

Code de sortie : 0 = lancer la configuration, 1 = ne pas la lancer (convention ExecCondition).
"""

from __future__ import annotations

import subprocess
import sys
import time

from berrycast.dev.nm import split_terse
from berrycast.setup.apply import BOOT_DIR, FORCE_FILE, wifi_connected

WAIT_FIRST_BOOT = 20
WAIT_KNOWN_WIFI = 120


def known_wifi_profiles() -> int:
    try:
        out = subprocess.run(["nmcli", "-t", "-f", "TYPE", "connection", "show"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    return sum(1 for line in out.splitlines() if split_terse(line)[0] == "802-11-wireless")


def should_start(connected, profiles: int, force: bool, sleep=time.sleep,
                 clock=time.monotonic) -> bool:
    """Décision (testable) : attend le Wi-Fi jusqu'au délai, sauf configuration forcée."""
    if force:
        return True
    deadline = clock() + (WAIT_KNOWN_WIFI if profiles else WAIT_FIRST_BOOT)
    while clock() < deadline:
        if connected():
            return False
        sleep(3)
    return not connected()


def main() -> int:
    force_path = BOOT_DIR / FORCE_FILE
    force = force_path.exists()
    start = should_start(wifi_connected, known_wifi_profiles(), force)
    print("Configuration au clavier : " + ("lancée" if start else "inutile (Wi-Fi connecté)"),
          file=sys.stderr)
    return 0 if start else 1


if __name__ == "__main__":
    sys.exit(main())
