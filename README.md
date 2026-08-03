# 🚀 Sooqify Image Updater

> **Automated Product Image Management for Sooqify & AlphaCode**

[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=flat-square&logo=windows)](https://github.com/)
[![License](https://img.shields.io/badge/License-Proprietary-red?style=flat-square)](./LICENSE)
[![Status](https://img.shields.io/badge/Status-Active%20Development-success?style=flat-square)]()

**Sooqify Image Updater** is a specialized Windows desktop application engineered for design teams. It automates the batch replacement of edited product images on **Sooqify** directly from organized local directories—eliminating manual overhead and zero coding required.

---

## ✨ Key Features

- 📁 **Automated Batch Replacement:** Instantly update product imagery based on structured local directory workflows.
- 🛡️ **Secure Product Verification:** Advanced style-code lookup and identity validation before executing any modifications.
- 🧪 **Dry Run / Preview Mode:** Inspect and verify all image mappings risk-free prior to live deployment.
- 🔄 **AlphaCode Central Sync:** Seamless synchronization with AlphaCode central systems (`sync.php`) paired with automated PDF performance reporting.
- 🛠️ **Developer Inspection Mode:** Real-time monitoring of image upload behaviors and payload delivery on the Sooqify dashboard.

---

## 📥 Download & Quick Start

Get the standalone executable—no Python environment or library dependencies required:

👉 **[Download Latest Release (.exe)](../../releases/latest)**

---

## ⚙️ Initial Setup

1. Download `sooqify-image-updater.exe` from the releases tab.
2. Launch the application and enter your **AlphaCode credentials**.
3. Target your local structured image directories.
4. Execute a **Dry Run** to validate product identities before committing changes live.

---

## 💻 Developer Guide

### Prerequisites
- Python 3.10+
- PySide6 / PyQt dependencies

### Local Setup
```bash
# Clone the repository
git clone [https://github.com/yswef/sooqify-image-updater.git](https://github.com/yswef/sooqify-image-updater.git)
cd sooqify-image-updater

# Install dependencies
pip install -r requirements.txt

# Run application
python main.py