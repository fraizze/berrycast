#!/bin/bash
# Met à jour BerryCast sur un Pi qui tourne déjà l'image de développement, SANS reflasher.
#
# Utilisation (sur le Pi) :
#   sudo bash dev-update.sh /tmp/bc      # /tmp/bc = copie du dépôt (archive décompressée)
#
# Ce que fait le script (mêmes étapes que la construction de l'image) :
# - remplace /opt/berrycast par la nouvelle version du code ;
# - installe les paquets manquants (s'il y a Internet) ;
# - met à jour les services systemd, le portail captif et la police console ;
# - redémarre l'écran HDMI.
# Il ne touche PAS au Wi-Fi ni à berrycast-wifi.txt : la connexion SSH reste ouverte.

set -euo pipefail

SRC="${1:?Indiquez le dossier de la copie du dépôt, par ex. /tmp/bc}"
if [ "$(id -u)" -ne 0 ]; then
	echo "À lancer avec sudo." >&2
	exit 1
fi
if [ ! -f "${SRC}/berrycast/__init__.py" ]; then
	echo "Pas de code BerryCast dans ${SRC}" >&2
	exit 1
fi

echo "1/5 Paquets nécessaires"
PKGS=$(sed -e 's/#.*//' "${SRC}/image/pi-gen/stage-berrycast/00-berrycast/00-packages" | xargs)
MISSING=""
for p in ${PKGS}; do
	dpkg-query -W -f '${Status}' "$p" 2>/dev/null | grep -q "install ok installed" || MISSING="${MISSING} $p"
done
if [ -n "${MISSING}" ]; then
	echo "   à installer :${MISSING}"
	apt-get update -qq && apt-get install -y -qq ${MISSING}
else
	echo "   déjà installés"
fi

echo "2/5 Code dans /opt/berrycast"
BUILD_INFO=""
[ -f /opt/berrycast/BUILD_INFO ] && BUILD_INFO=$(cat /opt/berrycast/BUILD_INFO)
rsync -a --delete --chown=0:0 --exclude .git --exclude .venv --exclude __pycache__ \
	"${SRC}/" /opt/berrycast/
chmod -R u=rwX,go=rX /opt/berrycast
if [ -f "${SRC}/BUILD_INFO" ]; then
	:
elif [ -n "${BUILD_INFO}" ]; then
	printf '%s\n' "${BUILD_INFO}" | sed 's/^commit=\(.*\)$/commit=\1+dev/' > /opt/berrycast/BUILD_INFO
fi

echo "3/5 Services systemd et portail captif"
install -m 644 "${SRC}"/system/dev/*.service /etc/systemd/system/
install -d -m 755 /etc/NetworkManager/dnsmasq-shared.d
install -m 644 "${SRC}/system/networkmanager/berrycast-captive.conf" /etc/NetworkManager/dnsmasq-shared.d/
systemctl daemon-reload

echo "4/5 Police console avec « ▀ » (QR code)"
PYTHONPATH=/opt/berrycast python3 -m berrycast.display.fontpatch \
	/usr/share/consolefonts/Lat15-TerminusBold32x16.psf.gz \
	/usr/share/berrycast/fonts/berrycast-32x16.psf

echo "5/5 Redémarrage de l'écran HDMI"
systemctl restart berrycast-devscreen.service
systemctl --no-pager --lines=0 status berrycast-devscreen.service | head -n 3

echo "Mise à jour terminée."
