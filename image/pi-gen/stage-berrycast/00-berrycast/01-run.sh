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
install -m 644 "${SRC}/system/dev/berrycast-devsetup.service" "${ROOTFS_DIR}/etc/systemd/system/"
install -m 644 "${SRC}/system/dev/berrycast-devscreen.service" "${ROOTFS_DIR}/etc/systemd/system/"
install -m 644 "${SRC}/system/dev/berrycast-setupui.service" "${ROOTFS_DIR}/etc/systemd/system/"

# Droits polkit minimaux de l'utilisateur berrycast (ex. : relancer la recherche des Wi-Fi)
install -d -m 755 "${ROOTFS_DIR}/etc/polkit-1/rules.d"
install -m 644 "${SRC}/system/polkit/50-berrycast.rules" "${ROOTFS_DIR}/etc/polkit-1/rules.d/"

# 3. Console : écran jamais éteint, curseur masqué, moins de messages du noyau sur l'écran
sed -i '1 s/$/ consoleblank=0 loglevel=3 vt.global_cursor_default=0/' \
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
usermod -a -G video,render berrycast
install -d -m 755 /var/lib/berrycast

# Aucun mot de passe connu : on verrouille celui (aléatoire) donné à la construction.
# Il sera défini par le développeur dans berrycast-wifi.txt.
usermod -p '!' ${FIRST_USER_NAME}

# Services : réglages au démarrage + écran HDMI (qui remplace l'invite de connexion sur tty1)
systemctl enable berrycast-devsetup.service berrycast-devscreen.service
systemctl mask getty@tty1.service

# cloud-init complètement désactivé (c'est berrycast-wifi.txt qui configure le Wi-Fi)
if [ -d /etc/cloud ]; then
	touch /etc/cloud/cloud-init.disabled
fi

# Modèle vide de berrycast-wifi.txt sur la partition de démarrage
PYTHONPATH=/opt/berrycast python3 -c "from berrycast.dev import wifi_file; open('/boot/firmware/berrycast-wifi.txt', 'w', encoding='utf-8', newline='').write(wifi_file.render())"
EOF
