"""Découverte Wi-Fi Direct pour Miracast (MS-MICE), via l'API D-Bus de wpa_supplicant.

Le Pi ne crée AUCUN groupe Wi-Fi Direct (NetworkManager les supprime, voir mice.py) : il
reste simplement « en écoute » pour que Windows + K le voie, comme à l'étape 02 (testé :
« BerryCast-Test » apparaissait dans Windows + K). À ses réponses, il ajoute :
- le nom affiché et le type d'appareil « TV » (P2PDeviceConfig) ;
- les éléments Wi-Fi Display (propriété globale WFDIEs) ;
- l'extension fabricant Microsoft MICE (P2PDeviceConfig « VendorExtension », placée par
  wpa_supplicant dans les réponses aux recherches : p2p_build_wps_ie, vérifié dans le code).

Droits : utilisateur « berrycast » dans le groupe « netdev » (règle D-Bus de wpa_supplicant).
"""

from __future__ import annotations

import logging

from berrycast.miracast import mice, wfd

log = logging.getLogger("berrycast.miracast.p2p")

WPA = "fi.w1.wpa_supplicant1"
WPA_PATH = "/fi/w1/wpa_supplicant1"
IFACE = WPA + ".Interface"
P2P = IFACE + ".P2PDevice"
PROPS = "org.freedesktop.DBus.Properties"
LISTEN_SECONDS = 120  # durée d'une période d'écoute (relancée avant la fin)


class P2PError(RuntimeError):
    pass


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

    def announce(self, device_name: str, hostname: str, ip: str | None) -> None:
        """Nom affiché dans Windows + K, type « TV », éléments WFD, capacité MICE."""
        dbus = self.dbus
        ext = mice.vendor_extension(hostname, ip)
        config = dbus.Dictionary({
            "DeviceName": dbus.String(device_name[:32]),
            "PrimaryDeviceType": dbus.Array(wfd.PRIMARY_DEVICE_TYPE_TV, signature="y"),
            "VendorExtension": dbus.Array([dbus.Array(ext, signature="y")], signature="ay"),
        }, signature="sv")
        self.iface.Set(P2P, "P2PDeviceConfig", config, dbus_interface=PROPS)
        self.wpa.Set(WPA, "WFDIEs", dbus.Array(wfd.WFD_IES, signature="y"),
                     dbus_interface=PROPS)
        log.info("Annoncé comme « %s » (Miracast MICE, %s / %s)", device_name, hostname,
                 ip or "IP inconnue")

    def listen(self) -> None:
        """(Re)met le Pi en écoute Wi-Fi Direct : Windows + K peut le découvrir."""
        self.iface.Listen(self.dbus.Int32(LISTEN_SECONDS), dbus_interface=P2P)

    def clear_announce(self) -> None:
        dbus = self.dbus
        for action in (
            lambda: self.wpa.Set(WPA, "WFDIEs", dbus.Array([], signature="y"),
                                 dbus_interface=PROPS),
            lambda: self.iface.Set(P2P, "P2PDeviceConfig", dbus.Dictionary(
                {"VendorExtension": dbus.Array([], signature="ay")}, signature="sv"),
                dbus_interface=PROPS),
            lambda: self.iface.StopFind(dbus_interface=P2P),
        ):
            try:
                action()
            except dbus.DBusException:
                pass
