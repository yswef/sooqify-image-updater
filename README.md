# 🚀 Sooqify Image Updater

> **Automated Product Image Management for Sooqify & AlphaCode**

[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=flat-square&logo=windows)](https://github.com/)
[![License](https://img.shields.io/badge/License-Proprietary-red?style=flat-square)](./LICENSE)
[![Status](https://img.shields.io/badge/Status-Active%20Development-success?style=flat-square)]()

**Sooqify Image Updater** is a specialized Windows desktop application engineered for design teams. It automates the batch replacement of edited product images on **Sooqify** directly from organized local directories—eliminating manual overhead and zero coding required.

---

## ⚠️ Repository visibility

This project is licensed **Proprietary** (see [`LICENSE`](./LICENSE)) - it should only ever live in a
**private** GitHub repository. If you're setting this up fresh, double-check the repo's visibility under
**Settings → General → Danger Zone** before pushing anything, and again after any GitHub org/ownership
change. A proprietary license does nothing on its own if the repository itself is public.

---

## ✨ Key Features

- 📁 **Automated Batch Replacement:** Instantly update product imagery based on structured local directory workflows.
- 🛡️ **Secure Product Verification:** Style-code lookup against the central AlphaCode sync system, with identity validation against Sooqify's own product ID before any modification is made.
- 🧪 **Dry Run / Preview Mode:** Inspect and verify all image mappings risk-free prior to live deployment.
- 🔄 **AlphaCode Central Sync:** Seamless synchronization with AlphaCode central systems (`sync.php`) paired with automated PDF performance reporting.
- 🛠️ **Developer Inspection Mode:** Real-time monitoring of image upload behaviors and payload delivery on the Sooqify dashboard (see `dev_tools/`).
- 🔒 **Isolated login:** Sooqify login happens once, inside a browser profile owned entirely by the app - never by copying or reusing your personal Chrome/Brave/Edge profile.

---

## 📥 Download & Quick Start

Get the standalone executable—no Python environment or library dependencies required:

👉 **[Download Latest Release (.exe)](../../releases/latest)**

---

## ⚙️ Initial Setup

1. Download `sooqify-image-updater.exe` from the releases tab.
2. Launch the application, pick your local root image folder, your browser, and your name; enter the
   AlphaCode sync URL/token if your team uses central sync.
3. Open **Settings → تسجيل الدخول لسوقيفاي** once and log into Sooqify in the window that opens, then close
   it. This uses a dedicated app-only browser profile (see *Browser profile* below) - your session is
   remembered automatically from then on.
4. Execute a **Dry Run** to validate product identities before committing changes live.

### Browser profile

The app never touches or copies your real Chrome/Brave/Edge profile. It keeps its own small, isolated
profile under `%APPDATA%\SooqifyImageUpdater\browser_profile`, with no personal extensions, history, or
sync data. You log into Sooqify inside it exactly once (via the Settings screen); after that, every dry
run and live run reuses that same profile directly - no per-run copying, no multi-minute startup delay.

---

## 💻 Developer Guide

### Prerequisites
- Python 3.10+
- A local Chrome, Brave, or Edge install (Playwright drives it via `channel=` / a discovered executable path - it does not bundle its own browser for this app)

### Local Setup
```bash
# Clone the repository (private - see "Repository visibility" above)
git clone https://github.com/yswef/sooqify-image-updater.git
cd sooqify-image-updater

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run application
python app/main.py
```

### `dev_tools/`
`dev_tools/` is intentionally excluded from version control via `.gitignore` (`dev_tools/`). It's a
developer-only inspection tool (network/DOM probe against the Sooqify admin panel) that isn't part of the
shipped app and isn't meant to be distributed with it - it stays local to each developer's machine. If you
need it, copy it in manually; it won't come back on a fresh clone or a future `git pull`, by design.

---

## 📦 Turning this into an .exe and publishing it on GitHub

You do **not** need to build the .exe yourself. `.github/workflows/build-windows-exe.yml` already does it
for you automatically, on a real Windows machine, every time you push:

1. Push your changes to the `main` branch on GitHub (a normal `git push`).
2. GitHub spins up a Windows runner, installs everything from `requirements.txt`, and runs
   `pyinstaller build/app.spec`.
3. Open the **Actions** tab on the repo → the latest "Build Windows EXE" run → once it's green, the
   `sooqify-image-updater-windows` artifact at the bottom of the run page contains the built `.exe`. That's
   downloadable immediately, no release needed.
4. To get it onto the **Releases** page instead (a proper versioned download link like
   `../../releases/latest`, which the top of this README links to), push a **tag** that starts with `v`:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
   The same workflow then also publishes the `.exe` as a GitHub Release automatically.

### Building it locally instead (optional)
Only needed if you want a copy without pushing to GitHub first:
```bash
pip install -r requirements.txt
pip install pyinstaller
playwright install chromium
pyinstaller build/app.spec
```
The finished file is `dist/SooqifyImageUpdater.exe`, already carrying the app's own icon
(`assets/icon.ico`).

