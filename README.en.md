# BerryCast

[Français](README.md) · **English**

> **Status: in development.** BerryCast is not usable yet.
> No image is available in the *Releases* for now.

BerryCast turns a **Raspberry Pi** plugged into a TV or monitor over HDMI into a **wireless display**:

- from a **Windows 10 or 11 PC**: press **Windows + K** ("Cast") and pick your BerryCast;
- from an **iPhone, iPad or Mac**: use **"Screen Mirroring"** and pick your BerryCast.

Nothing to install on the PC, iPhone or Mac. No command line needed.

## Supported Raspberry Pi models

Only models with **built-in Wi-Fi** are supported.

| Priority | Models | Image |
|---|---|---|
| 1 (main test device) | Raspberry Pi 3 Model B | arm64 |
| 1 | Pi 3 A+, 3 B+, 4 B, 5, Zero 2 W | arm64 |
| 2 (later, best effort) | Pi Zero W | armhf 32-bit |

Not supported: Pi 1, Pi 2, Pi Zero without "W" (no Wi-Fi).

## Installation

You need: a supported Raspberry Pi, a **microSD card** (8 GB or more), an HDMI cable,
the Pi's power supply, and a computer to prepare the card.

1. **Download the image**: open the [*Releases*](https://github.com/fraizze/berrycast/releases) page
   and download the latest `.img.xz` file. No need to unzip it.
2. **Install balenaEtcher** from [etcher.balena.io](https://etcher.balena.io/) (free, Windows / Mac / Linux).
3. **Flash the card**:
   - insert the microSD card into your computer;
   - open balenaEtcher;
   - click **"Flash from file"** and select the downloaded `.img.xz` file;
   - click **"Select target"** and select your microSD card (be careful not to pick another drive: it would be erased);
   - click **"Flash!"** and wait until it finishes.
4. **Plug in the Pi**: put the microSD card in the Pi, connect it to the TV over HDMI, then plug in the power.
5. **Follow the instructions shown on the TV**: on first boot, the screen shows a temporary Wi-Fi
   network to join with your phone, then a page where you choose the device name
   (for example "Living Room TV") and your home Wi-Fi.

Done: your BerryCast shows up in Windows + K and in the iPhone's Screen Mirroring list.

## Known limitations

- **No protected content (HDCP)**: Netflix, Disney+, some Blu-ray players, etc.
  will show a black screen. This is a deliberate limitation and will not be worked around.
- **One stream at a time**: if someone is already casting, you have to wait until they stop.

## Acknowledgements

The Miracast part is inspired by [lazycast](https://github.com/homeworkc/lazycast)
(Hsun-Wei Cho, GPL-3.0). The AirPlay part uses [UxPlay](https://github.com/FDH2/UxPlay) (GPL-3.0).

## License

BerryCast is free software, released under the **GNU GPL version 3 or any later version**
(`GPL-3.0-or-later`, see [LICENSE](LICENSE)).

Want to help? Read [CONTRIBUTING.md](CONTRIBUTING.md).
