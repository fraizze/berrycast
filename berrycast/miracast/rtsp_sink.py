"""Négociation RTSP Miracast côté récepteur (« sink »).

Le Pi se connecte au port RTSP 7236 de la source (le PC Windows), puis :
  M1  source -> OPTIONS            : on répond (méthodes acceptées)
  M2  sink   -> OPTIONS            : on demande les méthodes de la source
  M3  source -> GET_PARAMETER      : on donne nos capacités (vidéo, son, port RTP…)
  M4  source -> SET_PARAMETER      : la source annonce le format choisi
  M5  source -> SET_PARAMETER      : « wfd_trigger_method: SETUP » (ou TEARDOWN…)
  M6  sink   -> SETUP              : on ouvre la session (port UDP 1028)
  M7  sink   -> PLAY               : la vidéo commence (le lecteur est lancé avant)
  M16 source -> GET_PARAMETER vide : « tu es toujours là ? » (on répond 200 OK)
  M8  sink   -> TEARDOWN           : fin

Les messages sont traités selon leur type (et non dans un ordre figé), ce qui tolère
les petites variations entre versions de Windows. Tous les messages sont journalisés.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from collections.abc import Callable

from berrycast.miracast import wfd

log = logging.getLogger("berrycast.miracast.rtsp")

KEEPALIVE_TIMEOUT = 70  # secondes sans aucun message de la source -> fin de session
IDR_REQUEST_DELAYS = (0.0, 1.5, 3.0, 5.0, 8.0)  # après PLAY : le lecteur met ~2 s à démarrer


class RtspSink:
    def __init__(self, sock: socket.socket, source_ip: str, device_name: str,
                 on_play: Callable[[], None] | None = None,
                 on_stop: Callable[[], None] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 display: tuple[int, int] = (1920, 1080)):
        self.sock = sock
        self.display = display  # taille de l'écran : modes vidéo proposés à la source
        self.source_ip = source_ip
        self.device_name = device_name
        self.on_play = on_play or (lambda: None)
        self.on_stop = on_stop or (lambda: None)
        self.clock = clock
        self.parser = wfd.RtspParser()
        self.cseq = 0
        self.pending: dict[str, str] = {}  # CSeq de nos requêtes -> type (OPTIONS, SETUP…)
        self.presentation_url = f"rtsp://{source_ip}/wfd1.0/streamid=0"
        self.session = ""
        self.playing = False
        self.finished = False
        self.reason = ""
        self.formats: dict[str, str] = {}
        self.last_message = clock()
        self.stop_event = threading.Event()
        self.idr_due: list[float] = []  # moments où redemander une image complète

    # ---- Envoi ------------------------------------------------------------------

    def send(self, data: bytes) -> None:
        log.info("<<< envoi\n%s", data.decode(errors="replace").rstrip())
        self.sock.sendall(data)

    def request(self, method: str, url: str, kind: str, headers: dict | None = None,
                body: str = "") -> None:
        self.cseq += 1
        all_headers = {"CSeq": str(self.cseq)}
        all_headers.update(headers or {})
        self.pending[str(self.cseq)] = kind
        self.send(wfd.build(f"{method} {url} RTSP/1.0", all_headers, body))

    # ---- Réception ----------------------------------------------------------------

    def handle(self, msg: wfd.RtspMessage) -> None:
        log.info(">>> reçu\n%s\r\n\r\n%s", msg.first_line, msg.body.rstrip())
        self.last_message = self.clock()
        if msg.is_response:
            self.handle_response(msg)
        else:
            self.handle_request(msg)

    def handle_request(self, msg: wfd.RtspMessage) -> None:
        method = msg.method
        if method == "OPTIONS":  # M1
            self.send(wfd.response(msg.cseq, {
                "Public": "org.wfa.wfd1.0, SET_PARAMETER, GET_PARAMETER"}))
            self.request("OPTIONS", "*", "OPTIONS", {"Require": "org.wfa.wfd1.0"})  # M2
        elif method == "GET_PARAMETER":
            requested = msg.parameters()
            body = (wfd.answer_get_parameter(requested, self.device_name, self.display)
                    if requested else "")
            self.send(wfd.response(msg.cseq, body=body))  # M3, ou M16 si vide
        elif method == "SET_PARAMETER":
            values = msg.values()
            self.send(wfd.response(msg.cseq))
            trigger = values.get("wfd_trigger_method", "")
            if "wfd_presentation_URL" in values:  # M4
                url = values["wfd_presentation_URL"].split()[0]
                if url and url != "none":
                    self.presentation_url = url
            for key in ("wfd_video_formats", "wfd_audio_codecs"):
                if key in values:
                    self.formats[key] = values[key]
            if trigger == "SETUP":  # M5 -> M6
                self.request("SETUP", self.presentation_url, "SETUP", {
                    "Transport": f"RTP/AVP/UDP;unicast;client_port={wfd.RTP_PORT}"})
            elif trigger == "TEARDOWN":
                self.teardown("demandé par la source")
            elif trigger == "PLAY" and self.session:
                self.request("PLAY", self.presentation_url, "PLAY", {"Session": self.session})
        else:
            # Méthode inattendue : on répond poliment pour ne pas bloquer la source
            self.send(wfd.response(msg.cseq))

    def handle_response(self, msg: wfd.RtspMessage) -> None:
        kind = self.pending.pop(msg.cseq, "")
        if msg.status != 200:
            log.warning("Réponse %s à %s", msg.status, kind or "?")
            if kind in ("SETUP", "PLAY"):
                self.end(f"{kind} refusé ({msg.status})")
            return
        if kind == "SETUP":  # réponse à M6 -> lecteur prêt, puis M7
            self.session = wfd.session_id(msg.headers.get("session", ""))
            port = wfd.server_port(msg.headers.get("transport", ""))
            log.info("Session %s ouverte (port serveur %s)", self.session, port)
            self.on_play()
            self.request("PLAY", self.presentation_url, "PLAY", {"Session": self.session})
        elif kind == "PLAY":
            self.playing = True
            log.info("---- Négociation réussie : diffusion en cours ----")
            # Constaté sur le Pi : l'image complète (IDR, avec les réglages SPS/PPS) envoyée
            # juste après PLAY arrivait avant que le lecteur écoute ; ensuite Windows n'envoie
            # que des images « différentielles », impossibles à décoder. On la redemande
            # plusieurs fois pendant que le lecteur démarre.
            self.schedule_idr()
            self.send_due_idr()

    def schedule_idr(self) -> None:
        """Prévoit plusieurs demandes d'image complète (envoyées par la boucle run).

        Aussi appelé quand le lecteur est relancé : sans nouvelle image complète, il ne
        pourrait rien afficher."""
        start = self.clock()
        self.idr_due = [start + delay for delay in IDR_REQUEST_DELAYS]

    @property
    def video_profile(self) -> int | None:
        """Profil H.264 choisi par la source dans M4 (None si inconnu)."""
        return wfd.chosen_profile(self.formats.get("wfd_video_formats", ""))

    def request_idr(self) -> None:
        """Demande à la source une image complète (wfd_idr_request)."""
        self.request("SET_PARAMETER", "rtsp://localhost/wfd1.0", "IDR",
                     body="wfd_idr_request\r\n")

    def send_due_idr(self) -> None:
        now = self.clock()
        while self.idr_due and self.idr_due[0] <= now:
            self.idr_due.pop(0)
            self.request_idr()

    def teardown(self, reason: str) -> None:
        if self.session and not self.finished:
            try:
                self.request("TEARDOWN", self.presentation_url, "TEARDOWN",
                             {"Session": self.session})
            except OSError:
                pass
        self.end(reason)

    def end(self, reason: str) -> None:
        if not self.finished:
            self.finished = True
            self.reason = reason
            log.info("Fin de session : %s", reason)
            self.on_stop()

    def stop(self) -> None:
        """Arrêt demandé de l'extérieur (autre diffusion prioritaire, arrêt du service)."""
        self.stop_event.set()

    # ---- Boucle ----------------------------------------------------------------------

    def run(self) -> str:
        """Traite la session jusqu'à sa fin. Renvoie la raison de la fin."""
        self.sock.settimeout(0.5)
        try:
            while not self.finished:
                if self.stop_event.is_set():
                    self.teardown("arrêt demandé")
                    break
                if self.clock() - self.last_message > KEEPALIVE_TIMEOUT:
                    self.end("plus de nouvelles de la source")
                    break
                try:
                    self.send_due_idr()
                    data = self.sock.recv(4096)
                except TimeoutError:
                    continue
                except OSError as exc:
                    self.end(f"connexion perdue ({exc})")
                    break
                if not data:
                    self.end("connexion fermée par la source")
                    break
                for msg in self.parser.feed(data):
                    self.handle(msg)
                    if self.finished:
                        break
        finally:
            try:
                self.sock.close()
            except OSError:
                pass
        return self.reason
