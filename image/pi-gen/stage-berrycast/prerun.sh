#!/bin/bash -e
# Part du système de l'étape précédente (stage2 = Raspberry Pi OS Lite).

if [ ! -d "${ROOTFS_DIR}" ]; then
	copy_previous
fi
