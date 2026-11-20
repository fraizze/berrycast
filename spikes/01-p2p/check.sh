#!/usr/bin/env bash
# Diagnostic Wi-Fi Direct (P2P) pour BerryCast — prototype jetable (étape 02).
#
# Ce script NE MODIFIE RIEN : il se contente de lire l'état du système.
# Il ne coupe pas le Wi-Fi et ne touche pas à la connexion SSH.
#
# Confidentialité : les adresses MAC sont masquées, et le script n'affiche
# ni nom de réseau Wi-Fi (SSID), ni adresse IP, ni mot de passe.
#
# Utilisation (sur le Pi) :
#   sudo bash check.sh | tee check-result.txt

set -u
export LC_ALL=C

# Masque les adresses MAC (aa:bb:cc:dd:ee:ff -> xx:xx:xx:xx:xx:xx).
mask() {
    sed -E 's/([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}/xx:xx:xx:xx:xx:xx/g'
}

section() {
    printf '\n==================== %s ====================\n' "$1"
}

# Lance une commande, affiche son texte et sa sortie (masquée), sans s'arrêter en cas d'erreur.
run() {
    printf '\n$ %s\n' "$*"
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "(commande « $1 » introuvable)"
        return
    fi
    "$@" 2>&1 | mask
}

WPA=fi.w1.wpa_supplicant1
WPA_PATH=/fi/w1/wpa_supplicant1

section "0. Droits"
if [ "$(id -u)" -ne 0 ]; then
    echo "ATTENTION : lancez ce script avec sudo, sinon certaines informations manquent."
else
    echo "OK (root)"
fi

section "1. Système"
run cat /proc/device-tree/model; echo
run grep -E '^(PRETTY_NAME|VERSION_CODENAME)=' /etc/os-release
run uname -srm
run vcgencmd get_throttled
run vcgencmd measure_temp

section "2. Versions des paquets"
run dpkg-query -W -f '${Package} ${Version}\n' \
    wpasupplicant network-manager iw raspi-firmware firmware-brcm80211 \
    python3 python3-dbus python3-gi
run wpa_supplicant -v

section "3. Puce Wi-Fi (pilote et micrologiciel)"
run rfkill list
run iw reg get
if [ -r /sys/class/net/wlan0/device/driver ]; then
    echo; echo "Pilote de wlan0 : $(basename "$(readlink -f /sys/class/net/wlan0/device/driver)")"
fi
printf '\n$ dmesg | grep -i brcmf\n'
dmesg 2>&1 | grep -i brcmf | mask

section "4. Capacités de la puce (iw list) : modes et combinaisons"
# On garde seulement les blocs utiles : modes d'interface, combinaisons,
# commandes et fonctionnalités liées au P2P.
printf '\n$ iw list (extraits)\n'
if command -v iw >/dev/null 2>&1; then
    iw list 2>&1 | mask | awk '
        /Supported interface modes:/      { show = 1 }
        /software interface modes/        { show = 1 }
        /valid interface combinations:/   { show = 1 }
        /Supported commands:/             { show = 0 }
        /Band [0-9]+:/                    { show = 0 }
        /HT Capabilities|Frequencies:/    { show = 0 }
        show { print }
        /P2P|p2p/ && !show { print "  [P2P] " $0 }
    '
else
    echo "(commande « iw » introuvable)"
fi

section "5. Interfaces réseau actuelles"
printf '\n$ iw dev (sans SSID)\n'
iw dev 2>&1 | grep -v -i 'ssid' | mask
run ip -br link

section "6. wpa_supplicant : lancement et D-Bus"
run systemctl is-active wpa_supplicant.service
printf '\n$ systemctl cat wpa_supplicant.service | grep ExecStart\n'
systemctl cat wpa_supplicant.service 2>&1 | grep -E '^ExecStart'
printf '\n$ ps -o args= -C wpa_supplicant\n'
ps -o args= -C wpa_supplicant 2>&1 | mask
echo "(l'option -u signifie : API D-Bus activée)"

run busctl get-property "$WPA" "$WPA_PATH" "$WPA" Capabilities
run busctl get-property "$WPA" "$WPA_PATH" "$WPA" Interfaces
printf '\n$ busctl introspect %s %s (propriétés/méthodes globales)\n' "$WPA" "$WPA_PATH"
busctl introspect "$WPA" "$WPA_PATH" "$WPA" 2>&1 | mask

# Pour chaque interface gérée par wpa_supplicant : nom, présence de l'API P2P.
IFACES=$(busctl get-property "$WPA" "$WPA_PATH" "$WPA" Interfaces 2>/dev/null \
    | grep -o '"/[^"]*"' | tr -d '"')
for path in $IFACES; do
    echo
    echo "--- Interface D-Bus $path"
    busctl get-property "$WPA" "$path" "$WPA.Interface" Ifname 2>&1
    echo "Capacités (chercher \"p2p\" dans \"Modes\") :"
    busctl get-property "$WPA" "$path" "$WPA.Interface" Capabilities 2>&1
    if busctl introspect "$WPA" "$path" 2>/dev/null | grep -q "$WPA.Interface.P2PDevice"; then
        echo "API P2P (Interface.P2PDevice) : PRÉSENTE"
        printf 'P2PDeviceConfig : '
        busctl get-property "$WPA" "$path" "$WPA.Interface.P2PDevice" P2PDeviceConfig 2>&1 | mask
    else
        echo "API P2P (Interface.P2PDevice) : absente"
    fi
done

section "7. NetworkManager"
run nmcli --version
run nmcli -t -f RUNNING,STATE,WIFI-HW,WIFI general
run nmcli -t -f DEVICE,TYPE,STATE device
printf '\n$ NetworkManager --print-config (extraits)\n'
NetworkManager --print-config 2>&1 | grep -iE '^\[|unmanaged|plugins|backend|wifi' | mask
run ls /etc/NetworkManager/conf.d

section "8. Python (pour le prototype)"
run python3 --version
printf '\n$ python3 -c "import dbus"\n'
python3 -c 'import dbus; print("dbus-python", dbus.__version__)' 2>&1 | tail -1
printf '\n$ python3 -c "import gi"\n'
python3 -c 'import gi; gi.require_version("Gio", "2.0"); from gi.repository import Gio, GLib; print("PyGObject OK, GLib", GLib.glib_version)' 2>&1 | tail -1

section "Fin"
echo "Diagnostic terminé. Envoyez le fichier check-result.txt (ou son contenu)."
