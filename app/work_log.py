# =========================================================
# Sooqify Image Updater
# سجل العمل المحلي + الشكل الموحَّد لـ"وحدة عمل منجزة".
#
# لماذا JSON Lines (سطر لكل وحدة) ولا ملف JSON واحد؟
#   قراءة ملف JSON كامل وكتابته كاملاً هي الطريقة التي تفقد البيانات بأول كاتبين
#   متوازيين: كل كاتب يقرأ نسخة قديمة بالذاكرة ثم يكتبها فوق الأحدث، فتضيع كتابة
#   الآخر بلا أي خطأ. هنا الإضافة سطرٌ واحد بوضع "a" تحت قفل، فلا قراءة-تعديل-كتابة
#   أصلاً، ولو تعطّل التطبيق بمنتصف الكتابة يتلف سطر واحد لا الملف كله.
#
# هذا الملف نظير backend/app/services/work_units.py بمستودع AlphaCode - أي تعديل
# على الثوابت هنا يجب أن يُطبَّق هناك أيضاً (نفس نمط product_type_profiles.py).
# =========================================================
# تطوير: يوسف الحمزي

import datetime
import json
import os
import tempfile
import threading

import config as app_config

SCHEMA_VERSION = 1

WORK_LOG_FILENAME = "work_log.jsonl"
SYNC_STATE_FILENAME = "work_sync_state.json"

# ── العقد المشترك مع AlphaCode (يجب أن يطابق work_units.py حرفياً) ──
RECORD_KIND_FIELD = "record_kind"
RECORD_KIND_WORK_UNIT = "work_unit"

SOURCE_IMAGE_UPDATER = "image_updater"

ITEM_TYPE_IMAGES_UPDATED = "product_images_updated"

STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

_WRITE_LOCK = threading.RLock()


def get_work_log_path():
    return os.path.join(app_config.get_config_dir(), WORK_LOG_FILENAME)


def get_sync_state_path():
    return os.path.join(app_config.get_config_dir(), SYNC_STATE_FILENAME)


# ---------------------------------------------------------
# الشكل الموحَّد
# ---------------------------------------------------------

def make_work_unit(user, date, item_id, status=STATUS_DONE, quantity=1,
                   timestamp=None, item_type=ITEM_TYPE_IMAGES_UPDATED, extra=None):
    """
    يبني وحدة عمل بالشكل الموحَّد {source, user, date, item_type, item_id, status}.
    حقل `date` مقصود بهذا الاسم: هو نفس الحقل الذي تصفّي عليه تقارير AlphaCode،
    فتعمل النطاقات الأربعة (يوم/شهر/أيام متفرقة/مدى) على وحداتنا بلا أي تعديل هناك.
    """
    return {
        RECORD_KIND_FIELD: RECORD_KIND_WORK_UNIT,
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE_IMAGE_UPDATER,
        "user": str(user or ""),
        "date": str(date or "")[:10],
        "timestamp": str(timestamp or ""),
        "item_type": str(item_type or ""),
        "item_id": str(item_id or ""),
        "status": str(status or STATUS_DONE),
        "quantity": int(quantity or 0),
        **(extra or {}),
    }


def work_unit_key(unit):
    """
    مفتاح حتمي للوحدة بالأرشيف المشترك. حتميته تجعل إعادة الدفع idempotent:
    نفس الوحدة تُكتب فوق نفسها بدل أن تُحتسب مرتين بالتقرير.
    لا يبدأ بـ"_" عن قصد: مصالحة AlphaCode تستثني المفاتيح البادئة بـ"_" من الرفع.
    """
    return "WU::{source}::{item_type}::{item_id}::{date}".format(
        source=unit.get("source") or "unknown",
        item_type=unit.get("item_type") or "unknown",
        item_id=unit.get("item_id") or "unknown",
        date=(unit.get("date") or "")[:10] or "unknown",
    )


def now_parts():
    """(تاريخ YYYY-MM-DD، طابع زمني كامل) بوقت الجهاز."""
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------
# السجل المحلي (إضافة فقط)
# ---------------------------------------------------------

def append_unit(unit, logger=None):
    """
    يضيف وحدة عمل للسجل المحلي. يُنفَّذ **قبل** أي محاولة رفع ودائماً، حتى لو كانت
    المزامنة مطفأة أو الشبكة مقطوعة - السجل المحلي هو مصدر الحقيقة الذي تُصالح منه
    المزامنة لاحقاً، فلا يضيع عمل لأن الشبكة كانت مقطوعة لحظتها.
    يرجّع True لو كُتِب فعلاً.
    """
    path = get_work_log_path()
    line = json.dumps(unit, ensure_ascii=False)
    try:
        with _WRITE_LOCK:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return True
    except OSError as exc:
        # فشل الكتابة يُعلَن، لا يُبتلع: وحدة عمل غير مسجّلة = عمل لن يظهر بأي تقرير.
        if logger:
            logger.error("فشل تسجيل وحدة العمل بالسجل المحلي (%s): %s", path, exc)
        return False


def load_units(logger=None):
    """
    يقرأ كل وحدات العمل المسجّلة محلياً.
    الأسطر التالفة **تُعلَن بالسجل ولا تُتجاهل بصمت** - سطر تالف يعني وحدة عمل مفقودة
    من التقرير، وهذا بالضبط نوع الفشل الصامت الذي يجب أن يُرى.
    يرجّع: (قائمة الوحدات، عدد الأسطر التالفة)
    """
    path = get_work_log_path()
    units = []
    corrupt = 0
    if not os.path.isfile(path):
        return units, corrupt
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    unit = json.loads(raw)
                except ValueError:
                    corrupt += 1
                    if logger:
                        logger.warning("سطر تالف بسجل العمل المحلي رقم %s - وحدة عمل واحدة مفقودة.", line_number)
                    continue
                if isinstance(unit, dict) and unit.get(RECORD_KIND_FIELD) == RECORD_KIND_WORK_UNIT:
                    units.append(unit)
                else:
                    corrupt += 1
                    if logger:
                        logger.warning("سطر بسجل العمل المحلي رقم %s ليس وحدة عمل صالحة.", line_number)
    except OSError as exc:
        if logger:
            logger.error("تعذّر قراءة سجل العمل المحلي (%s): %s", path, exc)
    return units, corrupt


def units_by_key(units):
    """يحوّل قائمة وحدات لقاموس {مفتاح: وحدة}. التكرار يُطوى لأن المفتاح حتمي."""
    return {work_unit_key(unit): unit for unit in units}


# ---------------------------------------------------------
# حالة المزامنة المحلية (كتابة ذرّية)
# ---------------------------------------------------------

def load_sync_state():
    path = get_sync_state_path()
    default = {"last_reconcile_at": "", "last_error": "", "last_delta": None}
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            stored = json.load(handle)
        if isinstance(stored, dict):
            default.update(stored)
    except (OSError, ValueError):
        pass  # حالة تالفة تُعامَل كأنها لم تُكتب قط؛ أسوأ نتيجة هي مصالحة كاملة زائدة.
    return default


def save_sync_state(state):
    """
    كتابة ذرّية: ملف مؤقت بنفس المجلد ثم os.replace. بدونها انقطاع كهرباء بمنتصف
    الكتابة يترك ملفاً نصفياً، فتُقرأ الحالة افتراضية وتُعاد مصالحة كاملة بلا داعٍ.
    """
    path = get_sync_state_path()
    directory = os.path.dirname(path)
    handle = None
    try:
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".work_sync_state_", suffix=".tmp")
        handle = os.fdopen(fd, "w", encoding="utf-8")
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        os.replace(temp_path, path)
        return True
    except OSError:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        return False
