# =========================================================
# Sooqify Image Updater - حارس العقد المشترك مع AlphaCode
#
# `app/work_log.py` هنا و`backend/app/services/work_units.py` بمستودع AlphaCode
# يصفان **نفس** شكل وحدة العمل، لكنهما ملفان منفصلان بمستودعين منفصلين. لا توجد
# طريقة لاستيراد أحدهما من الآخر وقت التشغيل، فالتباعد ممكن بصمت - وتباعده يعني
# أن التطبيق يكتب مفاتيح لا يقرأها التقرير، فيختفي العمل من التقارير مرة أخرى.
#
# الحارس: بصمة sha256 للحقول المشتركة، **مثبَّتة بنفس القيمة بالملف النظير**.
# أي تعديل على الشكل يُسقط هذا الاختبار فوراً، ورسالة السقوط تقول صراحةً إن
# التعديل يجب أن يُطبَّق بالمستودع الآخر أيضاً ثم تُحدَّث البصمة بالطرفين.
# (نفس نمط product_type_profiles.py ↔ product_types.js المستخدم بالمشروع،
#  لكن بحارس آلي بدل تعليق يعتمد على الانتباه.)
# =========================================================

import hashlib
import json

import work_log

# ⚠️ هذه القيمة مكرَّرة عمداً بـ backend/tests/test_work_unit_contract.py
#    بمستودع AlphaCode. لا تُحدَّث بطرف واحد.
CONTRACT_FINGERPRINT = "a60d71e39cafe178"

DIVERGENCE_MESSAGE = (
    "تغيّر شكل وحدة العمل المشترك.\n"
    "هذا العقد مشترك مع backend/app/services/work_units.py بمستودع AlphaCode.\n"
    "طبّق نفس التعديل هناك، ثم حدّث CONTRACT_FINGERPRINT بـ**كلا** ملفي الاختبار.\n"
    "تركه غير متطابق يعني أن التطبيق يكتب مفاتيح لا يقرأها التقرير، فيختفي العمل من التقارير."
)


def _contract_shape():
    """الحقول التي يجب أن تتطابق حرفياً بين المستودعين."""
    unit = work_log.make_work_unit(user="u", date="2026-01-01", item_id="x")
    return {
        "record_kind_field": work_log.RECORD_KIND_FIELD,
        "record_kind_value": work_log.RECORD_KIND_WORK_UNIT,
        "schema_version": work_log.SCHEMA_VERSION,
        "source_image_updater": work_log.SOURCE_IMAGE_UPDATER,
        "item_type_images_updated": work_log.ITEM_TYPE_IMAGES_UPDATED,
        "statuses": sorted([work_log.STATUS_DONE, work_log.STATUS_FAILED, work_log.STATUS_SKIPPED]),
        "key_template": "WU::{source}::{item_type}::{item_id}::{date}",
        "unit_fields": sorted(unit.keys()),
    }


def _fingerprint(shape):
    return hashlib.sha256(
        json.dumps(shape, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


def test_the_shared_contract_has_not_drifted():
    assert _fingerprint(_contract_shape()) == CONTRACT_FINGERPRINT, DIVERGENCE_MESSAGE


def test_the_contract_values_are_the_exact_strings_the_other_side_reads():
    """
    تثبيت صريح للقيم النصية. البصمة وحدها تكشف التغيير لكنها لا تقول ما تغيّر؛
    هذه الأسطر تجعل السبب مقروءاً فوراً بمخرجات السقوط.
    """
    shape = _contract_shape()
    assert shape["record_kind_field"] == "record_kind"
    assert shape["record_kind_value"] == "work_unit"
    assert shape["source_image_updater"] == "image_updater"
    assert shape["item_type_images_updated"] == "product_images_updated"
    assert shape["statuses"] == ["done", "failed", "skipped"]
    assert shape["schema_version"] == 1
    assert shape["unit_fields"] == [
        "date", "item_id", "item_type", "quantity", "record_kind",
        "schema_version", "source", "status", "timestamp", "user",
    ]


def test_the_key_format_matches_the_documented_template():
    unit = work_log.make_work_unit(user="يوسف", date="2026-09-22", item_id="SC-1")
    assert work_log.work_unit_key(unit) == "WU::image_updater::product_images_updated::SC-1::2026-09-22"
