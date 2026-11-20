#!/usr/bin/env python3
"""Prototype JETABLE (étape 02) : faire apparaître le Pi dans Windows + K.

Ce que fait ce script, via l'API D-Bus de wpa_supplicant (sans toucher à NetworkManager) :
1. règle le nom Wi-Fi Direct (« BerryCast-Test ») et le type d'appareil « Écran / Télévision » ;
2. publie les éléments Wi-Fi Display (WFD) d'un récepteur (« sink ») : c'est ce qui fait
   apparaître l'appareil dans la liste « Diffuser » de Windows ;
3. se met à l'écoute Wi-Fi Direct (Listen, ou Find avec --mode find) ;
4. affiche (et enregistre) tous les événements Wi-Fi Direct : PC détecté, demande de
   connexion, PIN demandé… Les connexions ne sont PAS acceptées ici (étape 03).

Ctrl+C : arrête l'écoute et remet le nom et les éléments WFD comme avant.

Sources vérifiées (code source de wpa_supplicant 2.10/2.11, paquet Debian) :
- propriété globale WFDIEs (ay) : suite de sous-éléments « id (1 octet), longueur
  (2 octets, gros-boutiste), données » ; une valeur non vide active Wi-Fi Display
  (wpas_dbus_setter_global_wfd_ies -> wifi_display_subelem_set_from_ies) ;
- avec un « P2P Device » dédié (cas du Pi 3, voir iw dev), l'interface p2p-dev-wlan0
  n'a PAS d'objet D-Bus à elle : l'API Interface.P2PDevice et ses signaux passent par
  l'objet de wlan0 (wpa_supplicant.c : « if (iface->p2p_mgmt == 0) wpas_notify_iface_added » ;
  dbus_new.c : « if (parent->p2p_mgmt) parent = parent->parent ») ;
- PrimaryDeviceType : 8 octets (WPS_DEV_TYPE_LEN) ; catégorie 7 = écran, sous-catégorie 1 = TV
  (src/wps/wps_defs.h : WPS_DEV_DISPLAY = 7, WPS_DEV_DISPLAY_TV = 1) ;
- bits du « WFD Device Information » : Android AOSP WifiP2pWfdInfo.java
  (type d'appareil bits 0-1, 1 = récepteur principal ; session disponible = bit 4).

Utilisation (sur le Pi) :  sudo python3 p2p_listen.py
"""

from __future__ import annotations

import argparse
import signal
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Construction des données (fonctions pures, testées sur PC)
# ---------------------------------------------------------------------------

WFD_SUBELEM_DEVICE_INFO = 0
WFD_DEVICE_TYPE_PRIMARY_SINK = 0x0001  # bits 0-1 = 01 : récepteur principal (sink)
WFD_SESSION_AVAILABLE = 0x0010  # bits 4-5 = 01 : disponible pour une session
RTSP_CONTROL_PORT = 7236  # port RTSP standard de Miracast
MAX_THROUGHPUT_MBPS = 50  # débit maximal annoncé (prudent pour un Pi 3)

# Type d'appareil WPS : catégorie (2 octets) + OUI Wi-Fi Alliance 00:50:F2:04 + sous-catégorie
PRIMARY_DEVICE_TYPE_TV = bytes([0x00, 0x07, 0x00, 0x50, 0xF2, 0x04, 0x00, 0x01])

# Signification de dev_passwd_id dans GONegotiationRequest (identifiants WPS)
PASSWORD_IDS = {
    0: "PIN (par défaut)",
    1: "PIN saisi par l'utilisateur (keypad)",
    4: "bouton (PBC)",
    5: "PIN affiché par l'autre appareil (display)",
}


def wfd_device_info_subelement(
    port: int = RTSP_CONTROL_PORT, throughput: int = MAX_THROUGHPUT_MBPS
) -> bytes:
    """Sous-élément WFD n°0 « Device Information » d'un récepteur disponible.

    Format : id (1) | longueur = 6 (2) | device info (2) | port RTSP (2) | débit max Mb/s (2)
    """
    info = WFD_DEVICE_TYPE_PRIMARY_SINK | WFD_SESSION_AVAILABLE
    body = info.to_bytes(2, "big") + port.to_bytes(2, "big") + throughput.to_bytes(2, "big")
    return bytes([WFD_SUBELEM_DEVICE_INFO]) + len(body).to_bytes(2, "big") + body


def hexstr(data) -> str:
    return bytes(data).hex()


# ---------------------------------------------------------------------------
# Partie D-Bus (uniquement sur le Pi)
# ---------------------------------------------------------------------------

WPA = "fi.w1.wpa_supplicant1"
WPA_PATH = "/fi/w1/wpa_supplicant1"
IFACE = WPA + ".Interface"
P2P = IFACE + ".P2PDevice"
WPS = IFACE + ".WPS"
PEER = WPA + ".Peer"
PROPS = "org.freedesktop.DBus.Properties"


class Logger:
    def __init__(self, path: str | None):
        self.file = open(path, "a", encoding="utf-8") if path else None

    def __call__(self, message: str) -> None:
        line = f"{datetime.now():%H:%M:%S} {message}"
        print(line, flush=True)
        if self.file:
            self.file.write(line + "\n")
            self.file.flush()


def to_python(value):
    """Convertit les types dbus-python en types Python lisibles."""
    import dbus

    if isinstance(value, dbus.Array) and value.signature == "y":
        return hexstr(value)
    if isinstance(value, (dbus.Array, list)):
        return [to_python(v) for v in value]
    if isinstance(value, (dbus.Dictionary, dict)):
        return {str(k): to_python(v) for k, v in value.items()}
    if isinstance(value, dbus.Boolean):
        return bool(value)
    if isinstance(value, (dbus.String, dbus.ObjectPath)):
        return str(value)
    if isinstance(value, (dbus.Byte, dbus.Int16, dbus.Int32, dbus.Int64,
                          dbus.UInt16, dbus.UInt32, dbus.UInt64)):
        return int(value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ifname", default="wlan0", help="interface Wi-Fi (défaut : wlan0)")
    parser.add_argument("--name", default="BerryCast-Test", help="nom affiché dans Windows + K")
    parser.add_argument(
        "--mode", choices=("listen", "find"), default="listen",
        help="listen = rester visible (défaut) ; find = chercher + rester visible",
    )
    parser.add_argument("--timeout", type=int, default=120,
                        help="durée d'une période d'écoute, relancée automatiquement (s)")
    parser.add_argument("--log", default="p2p_listen.log", help="fichier journal")
    args = parser.parse_args()

    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib

    log = Logger(args.log)
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    wpa = bus.get_object(WPA, WPA_PATH)

    # 1. Objet D-Bus de l'interface Wi-Fi + vérification que l'API P2P répond
    try:
        path = wpa.GetInterface(args.ifname, dbus_interface=WPA)
    except dbus.DBusException as exc:
        log(f"ERREUR : wpa_supplicant ne gère pas {args.ifname} : {exc}")
        return 1
    iface = bus.get_object(WPA, path)
    try:
        old_config = iface.Get(P2P, "P2PDeviceConfig", dbus_interface=PROPS)
    except dbus.DBusException as exc:
        log(f"ERREUR : API Wi-Fi Direct (P2PDevice) indisponible sur {path} : {exc}")
        return 1
    old_wfd = wpa.Get(WPA, "WFDIEs", dbus_interface=PROPS)
    try:
        methods = iface.Get(WPS, "ConfigMethods", dbus_interface=PROPS)
    except dbus.DBusException:
        methods = "?"

    log(f"Interface : {args.ifname} -> {path}")
    log(f"Avant : nom P2P = {to_python(old_config).get('DeviceName')!r}, "
        f"WFDIEs = {hexstr(old_wfd) or '(vides)'}, méthodes WPS = {methods!r}")

    # 2. Nom + type d'appareil, puis éléments Wi-Fi Display
    new_config = dbus.Dictionary(
        {
            "DeviceName": dbus.String(args.name),
            "PrimaryDeviceType": dbus.Array(PRIMARY_DEVICE_TYPE_TV, signature="y"),
        },
        signature="sv",
    )
    iface.Set(P2P, "P2PDeviceConfig", new_config, dbus_interface=PROPS)
    wfd = wfd_device_info_subelement()
    wfd_dbus = dbus.Array(wfd, signature="y")
    wpa.Set(WPA, "WFDIEs", wfd_dbus, dbus_interface=PROPS)
    log(f"Nom P2P = {args.name!r}, type = écran/TV, WFDIEs = {hexstr(wfd)}")

    # 3. Écoute (relancée régulièrement)
    def start_listening() -> bool:
        try:
            if args.mode == "find":
                iface.Find(
                    dbus.Dictionary({"DiscoveryType": dbus.String("social")}, signature="sv"),
                    dbus_interface=P2P,
                )
            else:
                iface.Listen(dbus.Int32(args.timeout), dbus_interface=P2P)
        except dbus.DBusException as exc:
            log(f"ERREUR au lancement de l'écoute ({args.mode}) : {exc}")
        return True  # GLib : garder le minuteur

    def check_wfd() -> bool:
        """NetworkManager pourrait effacer nos éléments WFD : on les remet si besoin."""
        current = bytes(wpa.Get(WPA, "WFDIEs", dbus_interface=PROPS))
        if current != wfd:
            log(f"WFDIEs modifiés par un autre programme ({current.hex() or 'vides'}) : remis")
            wpa.Set(WPA, "WFDIEs", wfd_dbus, dbus_interface=PROPS)
        return True

    # 4. Affichage de tous les événements Wi-Fi Direct
    def peer_summary(peer_path) -> str:
        try:
            peer = bus.get_object(WPA, peer_path)
            props = peer.GetAll(PEER, dbus_interface=PROPS)
            name = str(props.get("DeviceName", "?"))
            dtype = hexstr(props.get("PrimaryDeviceType", b""))
            ies = props.get("IEs", [])
            return f"« {name} » (type {dtype}, IEs WFD : {hexstr(ies) or 'aucun'})"
        except dbus.DBusException:
            return str(peer_path)

    def on_signal(*sig_args, member=None):
        values = [to_python(a) for a in sig_args]
        detail = ""
        if member in ("DeviceFound", "DeviceLost") and sig_args:
            detail = peer_summary(sig_args[0]) if member == "DeviceFound" else str(sig_args[0])
        elif member == "GONegotiationRequest" and len(sig_args) >= 3:
            pid = int(sig_args[1])
            detail = (f"{peer_summary(sig_args[0])} méthode = {PASSWORD_IDS.get(pid, pid)}, "
                      f"intention GO = {int(sig_args[2])}  (acceptation : étape 03)")
        elif member and member.startswith("ProvisionDiscovery") and sig_args:
            detail = f"{peer_summary(sig_args[0])} {values[1:]}  (acceptation : étape 03)"
        else:
            detail = str(values)
        log(f"ÉVÉNEMENT {member} : {detail}")
        if member == "FindStopped" and args.mode == "find":
            start_listening()

    bus.add_signal_receiver(on_signal, dbus_interface=P2P, path=path, member_keyword="member")

    loop = GLib.MainLoop()

    def stop(*_):
        log("Arrêt : fin de l'écoute, remise des réglages d'origine…")
        try:
            iface.StopFind(dbus_interface=P2P)
        except dbus.DBusException:
            pass
        try:
            wpa.Set(WPA, "WFDIEs", dbus.Array(old_wfd, signature="y"), dbus_interface=PROPS)
            restore = {k: old_config[k] for k in ("DeviceName", "PrimaryDeviceType")
                       if k in old_config}
            if restore:
                iface.Set(P2P, "P2PDeviceConfig", dbus.Dictionary(restore, signature="sv"),
                          dbus_interface=PROPS)
        except dbus.DBusException as exc:
            log(f"Remise des réglages incomplète : {exc}")
        loop.quit()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGHUP, stop)  # connexion SSH coupée : on remet quand même tout en ordre

    start_listening()
    GLib.timeout_add_seconds(max(10, args.timeout - 5), start_listening)
    GLib.timeout_add_seconds(30, check_wfd)
    log(f"Prêt ({args.mode}). Sur le PC Windows : touches Windows + K. Ctrl+C pour arrêter.")
    loop.run()
    log("Terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
