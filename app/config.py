# =========================================================
# Sooqify Image Updater
# إعدادات أول تشغيل: مسار المجلد، المتصفح، بيانات المزامنة، واكتشاف وضع المطوّر.
# =========================================================
# تطوير: يوسف الحمزي

import json
import os
import tempfile

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
    """
    حفظ الإعدادات **بكتابة ذرّية**، ويعيد حساب DeveloperMode تلقائياً من الاسم المُدخل.

    لماذا الذرّية: الحفظ السابق كان يفتح config.json بوضع "w" (فيُفرَّغ فوراً) ثم يكتب.
    أي انقطاع بين الاثنين (تعطّل، إغلاق قسري، انقطاع كهرباء) يترك ملفاً نصفياً أو
    فارغاً، و`load_config` يبتلع JSONDecodeError ويرجع للقيم الافتراضية بصمت - أي
    يفقد RootFolder و SyncServerUrl و SyncToken دفعةً واحدة دون أن يلاحظ أحد.
    الآن: الكتابة تتم على ملف مؤقت بنفس المجلد ثم os.replace (عملية ذرّية على
    ويندوز ولينكس) - فالملف القديم يبقى سليماً حتى تكتمل الكتابة الجديدة.
    """
    merged = load_config()
    merged.update(config)
    # str() صريحة: الواجهة قد ترسل قيمة غير نصية (رقم/None)، و.strip() عليها كان
    # يرمي AttributeError ويُسقط الحفظ كاملاً.
    merged["DeveloperMode"] = (
        str(merged.get("OperatorName") or "").strip().lower() == DEVELOPER_NAME_TRIGGER
    )
    _save_json_atomic(get_config_path(), merged)
    return merged


def _save_json_atomic(path, payload):
    """كتابة JSON ذرّية: ملف مؤقت بنفس المجلد + fsync ثم os.replace."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    handle = None
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".config_", suffix=".tmp")
        handle = os.fdopen(fd, "w", encoding="utf-8")
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        if temp_path and os.path.exists(temp_path):
            # لا نترك ملفات مؤقتة متراكمة لو فشلت الكتابة.
            try:
                os.remove(temp_path)
            except OSError:
                pass


def is_setup_complete(config=None):
    config = config or load_config()
    return bool(config.get("SetupCompleted") and config.get("RootFolder"))