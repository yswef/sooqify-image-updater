# =========================================================
# Sooqify Image Updater
# إعدادات أول تشغيل: مسار المجلد، المتصفح، بيانات المزامنة، واكتشاف وضع المطوّر.
# =========================================================
# تطوير: يوسف الحمزي

import json
import os

APP_NAME = "SooqifyImageUpdater"

# دخول اسم "yousef" (بأي حالة أحرف) بحقل الاسم أول تشغيل يفتح وضع المطوّر تلقائياً.
DEVELOPER_NAME_TRIGGER = "yousef"

DEFAULT_CONFIG = {
    "RootFolder": "",
    "Browser": "chrome",          # chrome / brave / edge (يحدد أي متصفح يفتحه التطبيق فقط)
    "OperatorName": "",
    "DeveloperMode": False,
    "SyncEnabled": False,
    "SyncServerUrl": "",
    "SyncToken": "",
    "BatchLimit": 0,               # 0 = بلا حد أقصى (الافتراضي الموصى به)
    "SoundOnComplete": True,
    "SetupCompleted": False,
    "Headless": False,             # True = تشغيل المتصفح بدون نافذة مرئية (لازم على سيرفرات لينكس بلا شاشة)
    "MoveFoldersAfterUpload": True, # True = نقل المجلدات تلقائياً بعد الفراغ منها (ناجح/فاشل بتصنيف الخطأ)
}


def get_config_dir():
    """مجلد إعدادات التطبيق (خارج مجلد التثبيت، يبقى محفوظاً بين التحديثات)."""
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def get_config_path():
    return os.path.join(get_config_dir(), "config.json")


def get_log_dir():
    return os.path.join(get_config_dir(), "logs")


def load_config():
    """قراءة الإعدادات المحفوظة، مع دمج أي مفتاح افتراضي جديد لم يكن موجوداً بنسخة أقدم."""
    path = get_config_path()
    config = dict(DEFAULT_CONFIG)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                config.update(stored)
        except (json.JSONDecodeError, OSError):
            pass  # إعدادات تالفة - نستمر بالقيم الافتراضية بدل تعطيل التطبيق.
    return config


def save_config(config):
    """حفظ الإعدادات، ويعيد حساب DeveloperMode تلقائياً من الاسم المُدخل."""
    merged = load_config()
    merged.update(config)
    merged["DeveloperMode"] = (
        merged.get("OperatorName", "").strip().lower() == DEVELOPER_NAME_TRIGGER
    )
    with open(get_config_path(), "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return merged


def is_setup_complete(config=None):
    config = config or load_config()
    return bool(config.get("SetupCompleted") and config.get("RootFolder"))