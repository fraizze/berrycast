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
import os
import subprocess
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
NET_DIR = "/sys/class/net"
CTRL_DIR = "/run/wpa_supplicant"  # sockets de contrôle de wpa_supplicant (groupe netdev)
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

    def group_netdevs(self) -> list[str]:
        """Interfaces réseau des groupes Wi-Fi Direct présentes sur le système."""
        try:
            names = os.listdir(NET_DIR)
        except OSError:
            return []
        return sorted(n for n in names if is_group_ifname(n))

    def wpa_cli(self, ifname: str, *args: str) -> str:
        """Commande de contrôle de wpa_supplicant (secours quand D-Bus ne voit pas le groupe)."""
        try:
            return subprocess.run(["wpa_cli", "-p", CTRL_DIR, "-i", ifname, *args],
                                  capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    def managed(self, ifname: str) -> bool:
        """wpa_supplicant gère-t-il cette interface ?"""
        return self.wpa_cli(ifname, "ping") == "PONG"

    def find_group(self) -> tuple[str, str] | None:
        """(chemin D-Bus, nom) de l'interface du groupe existant, sinon None.

        Constaté sur le Pi : le groupe (p2p-wlan0-0) n'apparaît pas forcément dans la
        propriété « Interfaces » de wpa_supplicant. On part donc des interfaces réseau du
        système et on demande à wpa_supplicant leur objet D-Bus (GetInterface).
        """
        for name in self.group_netdevs():
            try:
                return str(self.wpa.GetInterface(name, dbus_interface=WPA)), name
            except self.dbus.DBusException:
                if self.managed(name):
                    return "", name  # géré, mais sans objet D-Bus : on passera par wpa_cli
        try:  # second moyen : la liste des interfaces de wpa_supplicant
            paths = self.wpa.Get(WPA, "Interfaces", dbus_interface=PROPS)
        except self.dbus.DBusException:
            return None
        for path in paths:
            try:
                obj = self.bus.get_object(WPA, path)
                name = str(obj.Get(IFACE, "Ifname", dbus_interface=PROPS))
            except self.dbus.DBusException:
                continue
            if is_group_ifname(name):
                return str(path), name
        return None

    def remove_orphans(self) -> None:
        """Supprime les interfaces de groupe que wpa_supplicant ne gère plus : la puce n'en
        accepte qu'une, une orpheline empêcherait de créer le groupe (« resource busy »)."""
        for name in self.group_netdevs():
            if self.managed(name):
                continue  # jamais supprimer un groupe que wpa_supplicant gère
            log.warning("Interface Wi-Fi Direct orpheline %s : suppression", name)
            subprocess.run(["iw", "dev", name, "del"], capture_output=True, check=False)

    def ensure_group(self, timeout: float = 20) -> tuple[str, str]:
        """Crée le groupe s'il n'existe pas ; renvoie (chemin D-Bus, nom d'interface)."""
        found = self.find_group()
        if found:
            self.group_path = found[0]
            return found
        self.remove_orphans()
        dbus = self.dbus
        try:  # découverte « progressive », comme lazycast (aide Windows à nous voir)
            self.iface.Find(dbus.Dictionary({"DiscoveryType": dbus.String("progressive")},
                                            signature="sv"), dbus_interface=P2P)
        except dbus.DBusException as exc:
            log.warning("P2P Find : %s", exc)
        freq = self.station_frequency()
        log.info("Création du groupe Wi-Fi Direct (fréquence %s)", freq or "auto")
        attempts = []
        if freq:  # même canal que la box d'abord, sinon wpa_supplicant choisit
            attempts.append({"persistent": dbus.Boolean(True), "frequency": dbus.Int32(freq)})
        attempts.append({"persistent": dbus.Boolean(True)})
        error = None
        for args in attempts:
            try:
                self.iface.GroupAdd(dbus.Dictionary(args, signature="sv"), dbus_interface=P2P)
                error = None
                break
            except dbus.DBusException as exc:
                error = exc
                log.warning("GroupAdd %s refusé : %s", dict(args), exc.get_dbus_message())
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = self.find_group()
            if found:  # même si GroupAdd a répondu une erreur, le groupe peut exister
                self.group_path = found[0]
                log.info("Groupe prêt : %s", found[1])
                return found
            if error is not None:
                break
            time.sleep(0.5)
        raise P2PError(f"création du groupe impossible ({error or 'pas apparu'})")

    def allow_pin(self, pin: str, ifname: str = "") -> None:
        """Accepte le prochain PC qui tape ce PIN (une seule fois)."""
        if self.group_path:
            group = self.bus.get_object(WPA, self.group_path)
            dbus = self.dbus
            group.Start(dbus.Dictionary({
                "Role": dbus.String("registrar"),
                "Type": dbus.String("pin"),
                "Pin": dbus.String(pin),
            }, signature="sv"), dbus_interface=WPS)
        elif ifname:
            # Même effet que « wps_pin any <PIN> » de lazycast ; renvoie le PIN si accepté
            answer = self.wpa_cli(ifname, "wps_pin", "any", pin)
            if answer != pin:
                raise P2PError(f"PIN refusé par wpa_supplicant : {answer or 'pas de réponse'}")
        else:
            raise P2PError("pas de groupe")
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
