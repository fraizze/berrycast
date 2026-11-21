#!/bin/bash -e
# Installe BerryCast (image de développement) dans le système de l'image.
# Exécuté par pi-gen sur la machine de construction ; ${ROOTFS_DIR} = racine de l'image.
# Le dossier files/berrycast (copie du dépôt) est préparé par GitHub Actions.

SRC="files/berrycast"
if [ ! -f "${SRC}/berrycast/__init__.py" ]; then
	echo "Copie du dépôt BerryCast introuvable dans ${SRC}" >&2
	exit 1
fi

# 1. Code du dépôt (y compris les prototypes spikes/) dans /opt/berrycast
install -d -m 755 "${ROOTFS_DIR}/opt/berrycast"
rsync -a --delete --chown=0:0 "${SRC}/" "${ROOTFS_DIR}/opt/berrycast/"
chmod -R u=rwX,go=rX "${ROOTFS_DIR}/opt/berrycast"

# 2. Services systemd de l'image de développement
install -m 644 "${SRC}"/system/dev/*.service "${SRC}"/system/dev/*.path 	"${ROOTFS_DIR}/etc/systemd/system/"

# Droits polkit minimaux de l'utilisateur berrycast (ex. : relancer la recherche des Wi-Fi)
install -d -m 755 "${ROOTFS_DIR}/etc/polkit-1/rules.d"
install -m 644 "${SRC}/system/polkit/50-berrycast.rules" "${ROOTFS_DIR}/etc/polkit-1/rules.d/"

# Tampon de réception UDP pour la vidéo Miracast (lu par systemd-sysctl au démarrage)
install -d -m 755 "${ROOTFS_DIR}/etc/sysctl.d"
install -m 644 "${SRC}/system/sysctl/90-berrycast.conf" "${ROOTFS_DIR}/etc/sysctl.d/"

# 3. Console : écran jamais éteint, curseur masqué, pas de messages du noyau ni de systemd
#    (« [ OK ] Reached target… ») par-dessus l'écran BerryCast (seules les erreurs restent)
sed -i '1 s/$/ consoleblank=0 loglevel=3 vt.global_cursor_default=0 systemd.show_status=error/' \
	"${ROOTFS_DIR}/boot/firmware/cmdline.txt"

on_chroot << EOF
set -e

# Utilisateur dédié (sans connexion possible) pour les services BerryCast
if ! id -u berrycast >/dev/null 2>&1; then
	useradd --system --user-group --no-create-home --home-dir /nonexistent \
		--shell /usr/sbin/nologin berrycast
fi
# Pas de groupe tty : c'est systemd qui ouvre l'écran tty1 pour le service (StandardOutput=tty).
# Groupes video et render : affichage graphique (interface de configuration pygame, vidéo).
# + netdev (Wi-Fi Direct via wpa_supplicant) et audio (son Miracast / AirPlay).
usermod -a -G video,render,netdev,audio berrycast
install -d -m 755 /var/lib/berrycast

# Aucun mot de passe connu : on verrouille celui (aléatoire) donné à la construction.
# Il sera choisi par le développeur : configuration au clavier sur la TV (ou berrycast-wifi.txt).
usermod -p '!' ${FIRST_USER_NAME}

# Services : berrycast-wifi.txt au démarrage, écran HDMI (à la place de l'invite de
# connexion sur tty1), configuration au clavier si pas de Wi-Fi, et son application (root)
systemctl enable berrycast-devsetup.service berrycast-devscreen.service 	berrycast-setupui.service berrycast-setup-apply.path 	berrycast-miracast.service berrycast-airplay.service
systemctl mask getty@tty1.service

# cloud-init complètement désactivé (c'est berrycast-wifi.txt qui configure le Wi-Fi)
if [ -d /etc/cloud ]; then
	touch /etc/cloud/cloud-init.disabled
fi

# Modèle vide de berrycast-wifi.txt sur la partition de démarrage
PYTHONPATH=/opt/berrycast python3 -c "from berrycast.dev import wifi_file; open('/boot/firmware/berrycast-wifi.txt', 'w', encoding='utf-8', newline='').write(wifi_file.render())"
EOF
