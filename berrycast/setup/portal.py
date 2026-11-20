"""Petit serveur web du mode configuration (portail captif), bibliothèque standard uniquement.

- Toute requête adressée à un AUTRE nom que 10.42.0.1 (captive.apple.com,
  connectivitycheck.gstatic.com, www.msftconnecttest.com…) est redirigée vers la page :
  c'est ce qui fait apparaître la page toute seule sur le téléphone.
- GET  /            : la page de configuration (HTML/CSS/JS sans framework)
- POST /api/verify  : vérifie le code à 6 chiffres affiché sur la TV
  (5 essais, puis blocage 1 minute ; réussite -> jeton de session)
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

log = logging.getLogger(__name__)

MAX_BODY = 4096


def new_verification_code() -> str:
    """Code à 6 chiffres, tiré au hasard de façon sûre."""
    return f"{secrets.randbelow(1_000_000):06d}"


def format_code(code: str) -> str:
    """« 123456 » -> « 123 456 » (plus lisible sur la TV)."""
    return f"{code[:3]} {code[3:]}"


class CodeGuard:
    """Vérification du code avec limite d'essais (protège contre les essais au hasard)."""

    def __init__(self, code: str, max_attempts: int = 5, lock_seconds: float = 60,
                 clock: Callable[[], float] = time.monotonic):
        self.code = code
        self.max_attempts = max_attempts
        self.lock_seconds = lock_seconds
        self.clock = clock
        self.failures = 0
        self.locked_until = 0.0
        self.tokens: set[str] = set()
        self._lock = threading.Lock()

    def locked_for(self) -> int:
        return max(0, round(self.locked_until - self.clock()))

    def verify(self, attempt: str) -> dict:
        with self._lock:
            if self.locked_for():
                return {"ok": False, "locked_seconds": self.locked_for(), "remaining": 0}
            attempt = "".join(ch for ch in str(attempt) if ch.isdigit())
            if secrets.compare_digest(attempt, self.code):
                self.failures = 0
                token = secrets.token_urlsafe(24)
                self.tokens.add(token)
                return {"ok": True, "token": token}
            self.failures += 1
            if self.failures >= self.max_attempts:
                self.failures = 0
                self.locked_until = self.clock() + self.lock_seconds
                return {"ok": False, "locked_seconds": self.locked_for(), "remaining": 0}
            return {"ok": False, "remaining": self.max_attempts - self.failures}

    def is_valid_token(self, token: str | None) -> bool:
        return bool(token) and token in self.tokens


def is_captive_check(host: str, own_address: str) -> bool:
    """Vrai si la requête vise un autre site que le Pi (test « Internet » du téléphone)."""
    hostname = host.split(":")[0].strip().lower()
    return bool(hostname) and hostname != own_address


def load_page() -> bytes:
    return resources.files("berrycast.setup").joinpath("static/index.html").read_bytes()


class Portal:
    """Serveur HTTP du portail. `context` fournit les infos affichées sur la page."""

    def __init__(self, guard: CodeGuard, address: str, port: int = 80,
                 context: Callable[[], dict] | None = None):
        self.guard = guard
        self.address = address
        self.port = port
        self.context = context or (lambda: {})
        self.page = load_page()
        self.server = ThreadingHTTPServer(("0.0.0.0", port), self._handler_class())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()
        log.info("Portail : http://%s:%s/", self.address, self.port)

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _handler_class(self):
        portal = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "BerryCast"

            def log_message(self, fmt, *args):  # journal plus discret
                log.debug("%s %s", self.address_string(), fmt % args)

            def _send(self, status, body: bytes, content_type: str, headers=None):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def _json(self, data: dict, status=HTTPStatus.OK):
                self._send(status, json.dumps(data).encode(), "application/json")

            def _redirect_to_portal(self):
                url = f"http://{portal.address}/"
                body = f'<a href="{url}">BerryCast</a>'.encode()
                self._send(HTTPStatus.FOUND, body, "text/html; charset=utf-8",
                           {"Location": url})

            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                if is_captive_check(self.headers.get("Host", ""), portal.address):
                    return self._redirect_to_portal()
                path = self.path.split("?")[0]
                if path in ("/", "/index.html"):
                    return self._send(HTTPStatus.OK, portal.page, "text/html; charset=utf-8")
                if path == "/api/info":
                    info = dict(portal.context())
                    info["locked_seconds"] = portal.guard.locked_for()
                    return self._json(info)
                return self._redirect_to_portal()

            def do_POST(self):
                if is_captive_check(self.headers.get("Host", ""), portal.address):
                    return self._redirect_to_portal()
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    return self._json({"error": "requête trop grande"},
                                      HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                try:
                    data = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    return self._json({"error": "JSON invalide"}, HTTPStatus.BAD_REQUEST)
                if self.path == "/api/verify":
                    result = portal.guard.verify(str(data.get("code", "")))
                    log.info("Code de vérification : %s", "correct" if result["ok"] else "faux")
                    return self._json(result)
                return self._json({"error": "inconnu"}, HTTPStatus.NOT_FOUND)

        return Handler
