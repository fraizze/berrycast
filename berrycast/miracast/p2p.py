"""Wi-Fi Direct (P2P) pour Miracast, via l'API D-Bus de wpa_supplicant.

Méthode (celle de lazycast, éprouvée avec Windows 10/11) :
1. le Pi s'annonce comme écran Miracast : nom, type d'appareil « TV », éléments WFD ;
2. il crée lui-même un groupe Wi-Fi Direct PERMANENT dont il est le chef (« GO ») :
   pas de négociation à chaque connexion, plus robuste ;
3. il accepte n'importe quel PC qui tape le bon code PIN (WPS « any ») : Windows
   affiche « Saisissez le code PIN pour votre appareil », le code est sur la TV.

Vérifié dans le code source de wpa_supplicant (2.10/2.11) :
- avec un « P2P Device » dédié (Pi 3), l'API Interface.P2PDevice est sur l'objet de wlan0 ;
- P2PDevice.GroupAdd({"persistent": True, "frequency": f}) crée le groupe ; l'interface
  du groupe (p2p-wlan0-0) apparaît dans la propriété globale « Interfaces » ;
- sur un GO, WPS.Start({"Type": "pin", "Pin": p}) appelle wpa_supplicant_ap_wps_pin
  (adresse NULL = n'importe quel appareil, sans délai d'expiration) ;
- propriété globale WFDIEs : sous-éléments WFD ; non vide = Wi-Fi Display activé.

Droits : l'utilisateur « berrycast » doit être dans le groupe « netdev » (règle D-Bus de
wpa_supplicant sur Debian/Raspberry Pi OS). Pas besoin de root.
"""

from __future__ import annotations

import logging
import time

from berrycast.miracast import wfd

log = logging.getLogger("berrycast.miracast.p2p")

WPA = "fi.w1.wpa_supplicant1"
WPA_PATH = "/fi/w1/wpa_supplicant1"
IFACE = WPA + ".Interface"
P2P = IFACE + ".P2PDevice"
WPS = IFACE + ".WPS"
BSS = WPA + ".BSS"
PROPS = "org.freedesktop.DBus.Properties"
GROUP_PREFIX = "p2p-"  # p2p-wlan0-0 (mais pas p2p-dev-wlan0, l'interface interne)


class P2PError(RuntimeError):
    pass


def is_group_ifname(name: str) -> bool:
    return name.startswith(GROUP_PREFIX) and not name.startswith("p2p-dev-")


class WifiDirect:
    def __init__(self, ifname: str = "wlan0", bus=None):
        import dbus  # paquet python3-dbus (importé ici : les tests tournent sans)

        self.dbus = dbus
        self.bus = bus or dbus.SystemBus()
        self.wpa = self.bus.get_object(WPA, WPA_PATH)
        self.ifname = ifname
        try:
            self.path = self.wpa.GetInterface(ifname, dbus_interface=WPA)
        except dbus.DBusException as exc:
            raise P2PError(f"wpa_supplicant ne gère pas {ifname} : {exc}") from exc
        self.iface = self.bus.get_object(WPA, self.path)
        self.group_path: str | None = None

    # ---- Annonce ------------------------------------------------------------------

    def announce(self, device_name: str) -> None:
        """Nom affiché dans Windows + K, type « TV », éléments Wi-Fi Display."""
        dbus = self.dbus
        config = dbus.Dictionary({
            "DeviceName": dbus.String(device_name[:32]),
            "PrimaryDeviceType": dbus.Array(wfd.PRIMARY_DEVICE_TYPE_TV, signature="y"),
            "PersistentReconnect": dbus.Boolean(True),  # PC déjà appairé : sans PIN
            "GOIntent": dbus.UInt32(15),
        }, signature="sv")
        self.iface.Set(P2P, "P2PDeviceConfig", config, dbus_interface=PROPS)
        self.wpa.Set(WPA, "WFDIEs", dbus.Array(wfd.WFD_IES, signature="y"),
                     dbus_interface=PROPS)
        log.info("Annoncé comme « %s » (écran Miracast)", device_name)

    def clear_announce(self) -> None:
        try:
            self.wpa.Set(WPA, "WFDIEs", self.dbus.Array([], signature="y"),
                         dbus_interface=PROPS)
        except self.dbus.DBusException:
            pass

    # ---- Groupe Wi-Fi Direct ------------------------------------------------------

    def station_frequency(self) -> int | None:
        """Fréquence (MHz) du Wi-Fi de la maison : le groupe se met sur le même canal
        (une seule radio sur le Pi : c'est le plus fiable)."""
        try:
            bss_path = self.iface.Get(IFACE, "CurrentBSS", dbus_interface=PROPS)
            if not bss_path or str(bss_path) == "/":
                return None
            bss = self.bus.get_object(WPA, bss_path)
            return int(bss.Get(BSS, "Frequency", dbus_interface=PROPS))
        except self.dbus.DBusException:
            return None

    def find_group(self) -> tuple[str, str] | None:
        """(chemin D-Bus, nom) de l'interface du groupe existant, sinon None."""
        paths = self.wpa.Get(WPA, "Interfaces", dbus_interface=PROPS)
        for path in paths:
            try:
                obj = self.bus.get_object(WPA, path)
                name = str(obj.Get(IFACE, "Ifname", dbus_interface=PROPS))
            except self.dbus.DBusException:
                continue
            if is_group_ifname(name):
                return str(path), name
        return None

    def ensure_group(self, timeout: float = 20) -> tuple[str, str]:
        """Crée le groupe s'il n'existe pas ; renvoie (chemin D-Bus, nom d'interface)."""
        found = self.find_group()
        if found:
            self.group_path = found[0]
            return found
        dbus = self.dbus
        try:  # découverte « progressive », comme lazycast (aide Windows à nous voir)
            self.iface.Find(dbus.Dictionary({"DiscoveryType": dbus.String("progressive")},
                                            signature="sv"), dbus_interface=P2P)
        except dbus.DBusException as exc:
            log.warning("P2P Find : %s", exc)
        args = {"persistent": dbus.Boolean(True)}
        freq = self.station_frequency()
        if freq:
            args["frequency"] = dbus.Int32(freq)
        log.info("Création du groupe Wi-Fi Direct (fréquence %s)", freq or "auto")
        try:
            self.iface.GroupAdd(dbus.Dictionary(args, signature="sv"), dbus_interface=P2P)
        except dbus.DBusException as exc:
            if freq:  # canal refusé : on laisse wpa_supplicant choisir
                log.warning("GroupAdd sur %s MHz refusé (%s), essai sans fréquence", freq, exc)
                self.iface.GroupAdd(dbus.Dictionary({"persistent": dbus.Boolean(True)},
                                                    signature="sv"), dbus_interface=P2P)
            else:
                raise P2PError(f"création du groupe impossible : {exc}") from exc
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = self.find_group()
            if found:
                self.group_path = found[0]
                log.info("Groupe prêt : %s", found[1])
                return found
            time.sleep(0.5)
        raise P2PError("le groupe Wi-Fi Direct n'est pas apparu")

    def allow_pin(self, pin: str) -> None:
        """Accepte le prochain PC qui tape ce PIN (une seule fois)."""
        if not self.group_path:
            raise P2PError("pas de groupe")
        group = self.bus.get_object(WPA, self.group_path)
        dbus = self.dbus
        group.Start(dbus.Dictionary({
            "Role": dbus.String("registrar"),
            "Type": dbus.String("pin"),
            "Pin": dbus.String(pin),
        }, signature="sv"), dbus_interface=WPS)
        log.info("Code PIN Miracast prêt")

    def remove_group(self) -> None:
        found = self.find_group()
        if not found:
            return
        try:
            group = self.bus.get_object(WPA, found[0])
            group.Disconnect(dbus_interface=P2P)
        except self.dbus.DBusException as exc:
            log.warning("Suppression du groupe : %s", exc)
        self.group_path = None
