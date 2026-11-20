"""Formulaire du premier lancement : données, navigation au clavier, vérifications.

Aucune dépendance graphique : tout est testable sur PC. L'affichage est fait par
berrycast.setup.ui (pygame), qui transmet les touches à SetupForm.handle().
"""

from __future__ import annotations

from dataclasses import dataclass, field

from berrycast.config import MAX_DEVICE_NAME_LENGTH, is_valid_device_name
from berrycast.dev.wifi_file import is_valid_psk
from berrycast.i18n import t
from berrycast.setup.keyboards import LAYOUTS

MANUAL = "__manual__"  # option « Autre réseau » de la liste des Wi-Fi
MIN_PI_PASSWORD = 8
MAX_LENGTHS = {"name": MAX_DEVICE_NAME_LENGTH, "wifi_manual": 32, "wifi_password": 64,
               "pi_password": 64, "pi_password2": 64}

# Actions renvoyées à l'interface
APPLY_KEYBOARD, REFRESH, SUBMITTED, QUIT = "apply_keyboard", "refresh", "submitted", "quit"


@dataclass
class Row:
    key: str
    label: str
    kind: str  # "choice", "text", "password", "button"
    value: str = ""
    options: list[tuple[str, str]] = field(default_factory=list)  # (valeur, texte affiché)
    error: str = ""
    hint: str = ""

    def option_index(self) -> int:
        values = [v for v, _ in self.options]
        return values.index(self.value) if self.value in values else -1

    def display_value(self) -> str:
        if self.kind == "password":
            return "•" * len(self.value)
        if self.kind == "choice":
            index = self.option_index()
            return self.options[index][1] if index >= 0 else self.hint
        return self.value


@dataclass
class Dropdown:
    row: Row
    index: int


class SetupForm:
    def __init__(self, networks: list[dict], countries: list[tuple[str, str]],
                 detected_country: str | None = None, keyboard_index: int = 0,
                 device_name: str = "BerryCast"):
        self.networks = networks
        self.rows_by_key: dict[str, Row] = {
            "keyboard": Row("keyboard", t("setup_keyboard"), "choice",
                            value=str(keyboard_index),
                            options=[(str(i), lay.label) for i, lay in enumerate(LAYOUTS)]),
            "name": Row("name", t("setup_name"), "text", value=device_name),
            "wifi": Row("wifi", t("setup_wifi"), "choice"),
            "refresh": Row("refresh", "", "button", value=t("setup_refresh")),
            "wifi_manual": Row("wifi_manual", t("setup_wifi_manual"), "text"),
            "wifi_password": Row("wifi_password", t("setup_wifi_password"), "password"),
            "country": Row("country", t("setup_country"), "choice",
                           value=detected_country or "", options=countries,
                           hint=t("setup_country_none")),
            "pi_password": Row("pi_password", t("setup_pi_password"), "password"),
            "pi_password2": Row("pi_password2", t("setup_pi_password2"), "password"),
            "submit": Row("submit", "", "button", value=t("setup_submit")),
        }
        self.set_networks(networks)
        self.focus = 0
        self.dropdown: Dropdown | None = None

    # ---- Contenu --------------------------------------------------------------

    def set_networks(self, networks: list[dict]) -> None:
        """Remplit la liste des Wi-Fi (garde le choix actuel s'il existe toujours)."""
        self.networks = networks
        row = self.rows_by_key["wifi"]
        options = []
        for n in networks:
            extra = f"   {n['signal']} %" + ("" if n["secure"] else "  · " + t("setup_open"))
            options.append((n["ssid"], n["ssid"] + extra))
        options.append((MANUAL, t("setup_wifi_manual_option")))
        row.options = options
        if row.value not in [v for v, _ in options]:
            row.value = networks[0]["ssid"] if networks else MANUAL
        row.hint = "" if networks else t("setup_no_networks")

    def network(self, ssid: str) -> dict | None:
        return next((n for n in self.networks if n["ssid"] == ssid), None)

    def needs_wifi_password(self) -> bool:
        wifi = self.rows_by_key["wifi"].value
        if wifi == MANUAL:
            return True  # inconnu : vide = réseau ouvert
        net = self.network(wifi)
        return bool(net and net["secure"])

    @property
    def rows(self) -> list[Row]:
        """Lignes visibles, dans l'ordre."""
        keys = ["keyboard", "name", "wifi", "refresh"]
        if self.rows_by_key["wifi"].value == MANUAL:
            keys.append("wifi_manual")
        if self.needs_wifi_password():
            keys.append("wifi_password")
        keys += ["country", "pi_password", "pi_password2", "submit"]
        return [self.rows_by_key[k] for k in keys]

    def focus_key(self, key: str) -> None:
        keys = [r.key for r in self.rows]
        if key in keys:
            self.focus = keys.index(key)

    @property
    def current(self) -> Row:
        rows = self.rows
        self.focus = max(0, min(self.focus, len(rows) - 1))
        return rows[self.focus]

    # ---- Clavier ----------------------------------------------------------------

    def handle(self, kind: str, value: str) -> str | None:
        """Traite une touche ("key", nom) ou ("char", caractère). Renvoie une action ou None."""
        if kind == "key" and value == "ctrl-c":
            return QUIT
        if self.dropdown:
            return self._handle_dropdown(kind, value)
        row = self.current
        if kind == "key":
            if value == "up":
                self.focus -= 1
            elif value in ("down", "tab"):
                self.focus += 1
            elif value == "enter":
                return self._enter(row)
            elif value in ("left", "right") and row.kind == "choice":
                return self._step_choice(row, -1 if value == "left" else 1)
            elif value == "backspace" and row.kind in ("text", "password"):
                row.value = row.value[:-1]
                row.error = ""
            elif value == "f5":
                return REFRESH
            self.focus = max(0, min(self.focus, len(self.rows) - 1))
            return None
        # caractère tapé
        if row.kind in ("text", "password"):
            if len(row.value) < MAX_LENGTHS.get(row.key, 64):
                row.value += value
                row.error = ""
        elif row.kind == "choice":
            self.dropdown = Dropdown(row, max(0, row.option_index()))
            return self._handle_dropdown("char", value)
        return None

    def _enter(self, row: Row) -> str | None:
        if row.kind == "choice":
            self.dropdown = Dropdown(row, max(0, row.option_index()))
            return None
        if row.key == "refresh":
            return REFRESH
        if row.key == "submit":
            return SUBMITTED if self.validate() else None
        self.focus += 1  # champ texte : Entrée passe au suivant
        return None

    def _step_choice(self, row: Row, step: int) -> str | None:
        if not row.options:
            return None
        index = (row.option_index() + step) % len(row.options)
        return self._select(row, index)

    def _select(self, row: Row, index: int) -> str | None:
        row.value = row.options[index][0]
        row.error = ""
        return APPLY_KEYBOARD if row.key == "keyboard" else None

    def _handle_dropdown(self, kind: str, value: str) -> str | None:
        dd = self.dropdown
        count = len(dd.row.options)
        if kind == "key":
            moves = {"up": -1, "down": 1, "pgup": -10, "pgdn": 10}
            if value in moves:
                dd.index = max(0, min(count - 1, dd.index + moves[value]))
            elif value == "home":
                dd.index = 0
            elif value == "end":
                dd.index = count - 1
            elif value == "esc":
                self.dropdown = None
            elif value == "enter":
                self.dropdown = None
                return self._select(dd.row, dd.index)
            return None
        # lettre tapée : aller à la prochaine option qui commence par cette lettre
        letter = value.casefold()
        for step in range(1, count + 1):
            i = (dd.index + step) % count
            if _fold(dd.row.options[i][1]).startswith(_fold(letter)):
                dd.index = i
                break
        return None

    # ---- Vérification et résultat ---------------------------------------------

    def validate(self) -> bool:
        for row in self.rows_by_key.values():
            row.error = ""
        r = self.rows_by_key
        if not is_valid_device_name(r["name"].value):
            r["name"].error = t("setup_err_name")
        wifi = r["wifi"].value
        if wifi == MANUAL:
            ssid = r["wifi_manual"].value.strip()
            if not ssid or len(ssid.encode()) > 32:
                r["wifi_manual"].error = t("setup_err_wifi")
            psk = r["wifi_password"].value
            if psk and not is_valid_psk(psk):
                r["wifi_password"].error = t("setup_err_psk")
        elif self.needs_wifi_password() and not is_valid_psk(r["wifi_password"].value):
            r["wifi_password"].error = t("setup_err_psk")
        pw = r["pi_password"].value
        if len(pw) < MIN_PI_PASSWORD or ":" in pw:
            r["pi_password"].error = t("setup_err_pi_short")
        elif pw != r["pi_password2"].value:
            r["pi_password2"].error = t("setup_err_pi_match")

        rows = self.rows
        errors = [i for i, row in enumerate(rows) if row.error]
        if errors:
            self.focus = errors[0]
        return not errors

    def result(self) -> dict:
        r = self.rows_by_key
        wifi = r["wifi"].value
        ssid = r["wifi_manual"].value.strip() if wifi == MANUAL else wifi
        return {
            "keyboard": LAYOUTS[int(r["keyboard"].value)],
            "device_name": r["name"].value.strip(),
            "ssid": ssid,
            "psk": r["wifi_password"].value if self.needs_wifi_password() else "",
            "country": r["country"].value or None,  # None = réglage international
            "pi_password": r["pi_password"].value,
        }


def _fold(text: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
