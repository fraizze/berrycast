"""Mode configuration (premier lancement) — étape A : point d'accès + portail + code.

Déroulé :
1. scan des Wi-Fi autour (AVANT le point d'accès : une seule radio) ;
2. Wi-Fi temporaire BerryCast-Setup-XXXX avec mot de passe aléatoire ;
3. portail web sur http://10.42.0.1 (s'ouvre tout seul sur le téléphone) ;
4. l'écran HDMI affiche tout ça (fichier d'état /run/berrycast/setup.json).

Étape A (test) : lancé à la main, s'arrête tout seul après --minutes et rétablit
le Wi-Fi d'avant (la connexion SSH revient). À lancer en root, via systemd-run pour
survivre à la coupure SSH (voir la procédure de test).
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
from pathlib import Path

from berrycast.setup import hotspot, state
from berrycast.setup.portal import CodeGuard, Portal, new_verification_code

log = logging.getLogger("berrycast.setup")

SCAN_FILE = Path(state.STATE_FILE).with_name("scan.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mode configuration BerryCast (étape A)")
    parser.add_argument("--minutes", type=float, default=10,
                        help="arrêt automatique après ce délai (défaut : 10 min)")
    parser.add_argument("--port", type=int, default=80)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    # 1. Scan avant de passer en point d'accès
    networks = hotspot.scan_networks()
    SCAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCAN_FILE.write_text(json.dumps(networks, ensure_ascii=False), encoding="utf-8")
    log.info("%d réseaux Wi-Fi détectés", len(networks))

    previous = hotspot.active_wifi_connection()
    ssid = hotspot.setup_ssid(hotspot.wifi_mac())
    password = hotspot.random_password()
    code = new_verification_code()
    url = f"http://{hotspot.AP_ADDRESS}"

    stop_event = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())

    state.write({"active": True, "ssid": ssid, "password": password, "url": url,
                 "code": code, "message": "Démarrage du Wi-Fi temporaire…"})
    portal = None
    try:
        hotspot.start_ap(ssid, password)
        guard = CodeGuard(code)
        portal = Portal(guard, hotspot.AP_ADDRESS, args.port,
                        context=lambda: {"ssid": ssid})
        portal.start()
        state.write({"active": True, "ssid": ssid, "password": password, "url": url,
                     "code": code, "message": ""})
        log.info("Mode configuration actif pour %.0f min (Wi-Fi %s)", args.minutes, ssid)
        stop_event.wait(args.minutes * 60)
    except Exception as exc:  # on rétablit toujours le Wi-Fi d'avant
        log.exception("Erreur du mode configuration : %s", exc)
    finally:
        if portal:
            portal.stop()
        hotspot.stop_ap(restore=previous)
        state.clear()
        log.info("Mode configuration terminé")
    return 0


if __name__ == "__main__":
    sys.exit(main())
