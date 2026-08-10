# =========================================================
# Sooqify Image Updater - PyInstaller build spec
# يبني تطبيق ونداوز (--onedir) قائم بذاته، يشمل:
#   - واجهة pywebview + ملفات UI (html/css/js/icon)
#   - محرّك Playwright الداخلي (driver) اللازم لتشغيل كرومّيوم
#   - متصفح Chromium نفسه (يُنسخ من مجلد ms-browsers الذي يجهّزه
#     خط البناء قبل هذا السكربت - راجع .github/workflows/build-windows-exe.yml)
# النتيجة: dist/SooqifyImageUpdater/ يعمل على أي جهاز ويندوز بدون
# بايثون أو أي تثبيت إضافي.
# =========================================================

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# جذر المشروع (هذا الملف داخل build/، فنطلع مجلد واحد للأعلى)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), ".."))

APP_DIR = os.path.join(PROJECT_ROOT, "app")
UI_DIR = os.path.join(APP_DIR, "ui")
ICON_PATH = os.path.join(UI_DIR, "assets", "icon.ico")

# مجلد متصفحات Playwright المُجهّز مسبقاً بخط البناء (PLAYWRIGHT_BROWSERS_PATH).
# لو ما كان موجوداً (مثلاً بناء محلي سريع بدون هذه الخطوة) نتجاوزه بدون كسر البناء -
# بس بذا الحال لازم Chromium يكون مثبّت أصلاً على جهاز التشغيل.
BROWSERS_DIR = os.path.join(PROJECT_ROOT, "ms-browsers")

datas = [
    (UI_DIR, "app/ui"),
]
if os.path.isdir(BROWSERS_DIR):
    datas.append((BROWSERS_DIR, "ms-browsers"))

binaries = []
hiddenimports = [
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "clr_loader",
    "pythonnet",
]

# collect_all يجمع تلقائياً كل ملفات/بيانات/استيرادات الحزمة (بما فيها driver
# الخاص بـ Playwright اللازم لتشغيل كرومّيوم من خارج بيئة بايثون).
for pkg in ("playwright", "webview"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    [os.path.join(APP_DIR, "main.py")],
    pathex=[APP_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SooqifyImageUpdater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=ICON_PATH if os.path.isfile(ICON_PATH) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="SooqifyImageUpdater",
)
