#!/bin/bash
# Met à jour BerryCast sur un Pi qui tourne déjà l'image de développement, SANS reflasher.
#
# Utilisation (sur le Pi) :
#   sudo bash dev-update.sh /tmp/bc      # /tmp/bc = copie du dépôt (archive décompressée)
#
# Ce que fait le script (mêmes étapes que la construction de l'image) :
# - installe les paquets manquants (s'il y a Internet) ;
# - remplace /opt/berrycast par la nouvelle version du code ;
# - met à jour les services systemd, les droits polkit et les groupes ;
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
missing() {  # paquets de la liste $1 qui ne sont pas encore installés
	[ -f "$1" ] || return 0
	for p in $(sed -e 's/#.*//' "$1" | xargs); do
		dpkg-query -W -f '${Status}' "$p" 2>/dev/null | grep -q "install ok installed" || echo "$p"
	done
}
PKG_DIR="${SRC}/image/pi-gen/stage-berrycast/00-berrycast"
MISSING=$(missing "${PKG_DIR}/00-packages" | xargs)
MISSING_NR=$(missing "${PKG_DIR}/00-packages-nr" | xargs)
if [ -n "${MISSING}${MISSING_NR}" ]; then
	echo "   à installer : ${MISSING} ${MISSING_NR}"
	echo "   (cela peut prendre plusieurs minutes, la progression s'affiche ci-dessous)"
	apt-get update
	[ -z "${MISSING}" ] || apt-get install -y ${MISSING}
	[ -z "${MISSING_NR}" ] || apt-get install -y --no-install-recommends ${MISSING_NR}
else
	echo "   déjà installés"
fi

echo "2/5 Code dans /opt/berrycast"
BUILD_INFO=""
[ -f /opt/berrycast/BUILD_INFO ] && BUILD_INFO=$(cat /opt/berrycast/BUILD_INFO)
rsync -a --delete --chown=0:0 --exclude .git --exclude .venv --exclude __pycache__ \
	"${SRC}/" /opt/berrycast/
chmod -R u=rwX,go=rX /opt/berrycast
if [ ! -f "${SRC}/BUILD_INFO" ] && [ -n "${BUILD_INFO}" ]; then
	printf '%s\n' "${BUILD_INFO}" | sed 's/^commit=\([^+]*\).*$/commit=\1+dev/' \
		> /opt/berrycast/BUILD_INFO
fi

echo "3/5 Services systemd, droits polkit, groupes"
install -m 644 "${SRC}"/system/dev/*.service "${SRC}"/system/dev/*.path /etc/systemd/system/
install -d -m 755 /etc/polkit-1/rules.d
install -m 644 "${SRC}/system/polkit/50-berrycast.rules" /etc/polkit-1/rules.d/
usermod -a -G video,render berrycast
systemctl daemon-reload
systemctl enable berrycast-setupui.service berrycast-setup-apply.path
systemctl start berrycast-setup-apply.path

echo "4/5 Nettoyage des essais précédents"
rm -f /etc/NetworkManager/dnsmasq-shared.d/berrycast-captive.conf
rm -rf /usr/share/berrycast/fonts

echo "5/5 Redémarrage de l'écran HDMI"
systemctl restart berrycast-devscreen.service
systemctl --no-pager --lines=0 status berrycast-devscreen.service | head -n 3

echo "Mise à jour terminée."
