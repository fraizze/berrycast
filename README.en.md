# BerryCast

[Français](README.md) · **English**

BerryCast turns a **Raspberry Pi** plugged into a TV over HDMI into a **wireless display**:

- 💻 from a **Windows 10 or 11 PC**: press **Windows + K** ("Cast"), then pick your BerryCast;
- 📱 from an **iPhone, iPad or Mac**: use **Screen Mirroring**, then pick your BerryCast.

Nothing to install on the PC or the iPhone. No command line needed to use it.

![status: in development](docs/images/badges/status-en.svg)
![Windows + K: works](docs/images/badges/windows-en.svg)
![iPhone / iPad / Mac: works](docs/images/badges/iphone-en.svg)
![Raspberry Pi 3, 4, 5, Zero 2 W](docs/images/badges/raspberry.svg)
![license GPL-3.0+](docs/images/badges/license-en.svg)

> [!NOTE]
> **In development.** Windows + K and iPhone mirroring (portrait and landscape) work on a
> Raspberry Pi 3 B. A **development image** is published in the
> [*Releases*](https://github.com/fraizze/berrycast/releases) ("dev" pre-release).

## 🍓 Supported models

Only models with **built-in Wi-Fi** work.

| Model | Status |
|---|---|
| Raspberry Pi 3 Model B | ✅ tested (main model) |
| Pi 3 A+, 3 B+, 4 B, 5, Zero 2 W | 🟡 planned, not tested yet |
| Pi Zero W | ⏳ later ("best effort") |
| Pi 1, Pi 2, Zero without "W" | ❌ no Wi-Fi |

## 🚀 Installation

You need: a supported Raspberry Pi, a **microSD card** (8 GB or more), an **HDMI** cable,
the Pi's power supply, a **USB keyboard** (for the first start) and a computer.

1. **Download the image** `berrycast-dev-….img.xz` from the
   [*Releases*](https://github.com/fraizze/berrycast/releases). No need to unzip it.
2. **Flash it** to the microSD card with [balenaEtcher](https://etcher.balena.io/):
   *Flash from file* → *Select target* (your microSD card) → *Flash!*
3. **Plug in** the microSD card, the USB keyboard, the HDMI cable, then the power supply.
4. **Fill in the form on the TV** with the keyboard: keyboard layout, device name
   (e.g. "Living Room"), Wi-Fi, Wi-Fi password, country.

> [!TIP]
> No keyboard? Fill in the `berrycast-wifi.txt` file on the microSD card with a text editor
> before the first start (see [docs/image-dev.md](docs/image-dev.md), in French).

## 📺 Casting

| From | Do | Code |
|---|---|---|
| 💻 Windows 10 / 11 PC | **Windows + K**, then "Living Room" | none (the PC must be on the same Wi-Fi) |
| 📱 iPhone / iPad / Mac | **Screen Mirroring**, then "Living Room" | 4 digits shown in large type on the TV, the first time |

## ⚠️ Known limitations

> [!WARNING]
> - **No protected content** (Netflix, Disney+, Prime Video…): it will show a black screen or an
>   error message. These services require copy protection (HDCP on Windows, FairPlay on Apple)
>   that is reserved for certified, licensed devices; free software cannot obtain it, and
>   bypassing it would be illegal. Watch them with the TV's own app instead.
> - **One cast at a time.**
> - On a **Pi 3**, the Windows picture is **720p** (its 2.4 GHz Wi-Fi is not enough for smooth 1080p).

## 🛠️ For developers

Update a Pi **without reflashing** (🖥️ PC — PowerShell, one command at a time):

```powershell
git -C C:\Users\<your-name>\code\berrycast archive --format=tar.gz -o "$env:TEMP\berrycast.tgz" HEAD
```

```powershell
scp "$env:TEMP\berrycast.tgz" pi@berrycast.local:/tmp/
```

```powershell
ssh -t pi@berrycast.local "rm -rf /tmp/bc && mkdir -p /tmp/bc && tar xzf /tmp/berrycast.tgz -C /tmp/bc && sudo bash /tmp/bc/scripts/dev-update.sh /tmp/bc"
```

Read the Windows casting log:

```powershell
ssh pi@berrycast.local "sudo journalctl -u berrycast-miracast --since '-5min' --no-pager | tail -n 40"
```

Details (in French): [docs/image-dev.md](docs/image-dev.md) · [docs/test-diffusion.md](docs/test-diffusion.md) ·
want to help? [CONTRIBUTING.md](CONTRIBUTING.md)

## 🙏 Credits and license

Miracast is inspired by [lazycast](https://github.com/homeworkc/lazycast) (Hsun-Wei Cho, GPL-3.0);
AirPlay uses [UxPlay](https://github.com/FDH2/UxPlay) (GPL-3.0).

BerryCast is free software under the **GPL-3.0-or-later** license ([LICENSE](LICENSE)).
