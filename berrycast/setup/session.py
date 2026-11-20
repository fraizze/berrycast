"""Déroulé du premier lancement, commun aux deux affichages (texte et graphique).

États : « form » (formulaire) -> « applying » (connexion en cours) -> « done » (prêt),
ou retour à « form » avec un message d'erreur si la connexion échoue.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from berrycast.i18n import t
from berrycast.setup import apply as apply_mod
from berrycast.setup import keyboards
from berrycast.setup.form import APPLY_KEYBOARD, QUIT, REFRESH, SUBMITTED, SetupForm

ERROR_MESSAGES = {
    "wrong_password": "setup_err_wrong_password",
    "not_found": "setup_err_not_found",
    "timeout": "setup_err_timeout",
    "invalid": "setup_err_invalid",
    "failed": "setup_err_failed",
}


class Session:
    def __init__(self, form: SetupForm,
                 scan: Callable[[bool], list[dict]],
                 submit: Callable[[dict], dict] = apply_mod.submit,
                 apply_keyboard: Callable[[keyboards.Layout], bool] = keyboards.apply):
        self.form = form
        self.scan = scan
        self.submit = submit
        self.apply_keyboard = apply_keyboard
        self.state = "form"
        self.notice = ""  # message en bas de l'écran
        self.notice_until = 0.0
        self.error = ""  # erreur de connexion, affichée en haut du formulaire
        self.result: dict = {}
        self.busy = ""  # texte « en cours… » (recherche des Wi-Fi)
        self._worker: threading.Thread | None = None

    # ---- Clavier ------------------------------------------------------------------

    def handle(self, kind: str, value: str) -> bool:
        """Traite une touche. Renvoie False pour quitter."""
        if self.state == "done":
            return not (kind == "key" and value in ("enter", "esc", "ctrl-c"))
        if self.state == "applying" or self.busy:
            return True  # on attend la fin de l'opération en cours
        action = self.form.handle(kind, value)
        if action == APPLY_KEYBOARD:
            self.keyboard_changed()
        elif action == REFRESH:
            self.start(self._refresh, t("setup_refreshing"))
        elif action == SUBMITTED:
            self.error = ""
            self.state = "applying"
            self.start(self._apply)
        elif action == QUIT:
            return False
        return True

    def keyboard_changed(self) -> None:
        layout = keyboards.LAYOUTS[int(self.form.rows_by_key["keyboard"].value)]
        if not self.apply_keyboard(layout):
            self.notify(t("setup_keyboard_failed"))

    def notify(self, message: str, seconds: float = 5) -> None:
        self.notice = message
        self.notice_until = time.monotonic() + seconds

    def notice_visible(self) -> bool:
        return bool(self.notice) and time.monotonic() < self.notice_until

    # ---- Opérations longues (en arrière-plan : l'écran reste à jour) -------------

    def start(self, target: Callable[[], None], busy: str = "") -> None:
        self.busy = busy
        self._worker = threading.Thread(target=self._run, args=(target,), daemon=True)
        self._worker.start()

    def _run(self, target: Callable[[], None]) -> None:
        try:
            target()
        finally:
            self.busy = ""

    def wait(self, timeout: float | None = None) -> None:
        """Attend la fin de l'opération en cours (utile pour les tests)."""
        if self._worker:
            self._worker.join(timeout)

    def _refresh(self) -> None:
        self.form.set_networks(self.scan(True))

    def _apply(self) -> None:
        res = self.form.result()
        request = {
            "keyboard_layout": res["keyboard"].layout,
            "keyboard_variant": res["keyboard"].variant,
            "device_name": res["device_name"],
            "ssid": res["ssid"],
            "psk": res["psk"],
            "country": res["country"],
            "pi_password": res["pi_password"],
        }
        try:
            result = self.submit(request)
        except OSError as exc:
            result = {"ok": False, "error": "failed", "details": [str(exc)]}
        self.result = result
        if result.get("ok"):
            self.state = "done"
        else:
            key = ERROR_MESSAGES.get(result.get("error", "failed"), "setup_err_failed")
            self.error = t(key, ssid=res["ssid"])
            self.state = "form"
            if result.get("error") == "wrong_password":
                self.form.focus_key("wifi_password")
