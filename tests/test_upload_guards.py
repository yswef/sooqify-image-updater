# =========================================================
# Sooqify Image Updater - حرّاس الرفع والأرشفة والإعدادات
#
# كل اختبار هنا يحرس عيباً **مُثبَتاً** سابقاً. أي عودة للسلوك القديم تُسقطه فوراً.
# =========================================================

import json
import os

import pytest

import config as app_config
import uploader


# ---------------------------------------------------------
# صفحة متصفح وهمية تحاكي ما يهمّنا من Playwright
# ---------------------------------------------------------

class FakeElement:
    def __init__(self, files=0, accepts=True):
        self.files = files
        self.accepts = accepts

    def set_input_files(self, path):
        if self.accepts:
            self.files += 1

    def evaluate(self, script):
        if "files" in script:
            return self.files
        return ""

    def wait_for(self, **kwargs):
        pass


class FakeLocator:
    def __init__(self, elements):
        self._elements = list(elements)

    def count(self):
        return len(self._elements)

    def nth(self, index):
        return self._elements[index]

    @property
    def first(self):
        return self._elements[0]

    def set_input_files(self, path):
        self._elements[0].set_input_files(path)

    def wait_for(self, **kwargs):
        if not self._elements:
            raise TimeoutError("not attached")


class FakePage:
    """
    يحاكي صفحة التعديل: حقل رئيسي واحد + عدد قابل للضبط من حقول المعرض.
    `gallery_slots` = كم حقل معرض فاضٍ متاح فعلاً (0 يعني أن الصفحة لم تبنِها).
    """

    def __init__(self, gallery_slots=5, main_accepts=True, old_images=0, url=None):
        self.url = url or "https://admin.sooqifyonline.com/admin/item/edit/1"
        self.main = FakeElement(accepts=main_accepts)
        self.gallery = [FakeElement() for _ in range(gallery_slots)]
        self.old_images = old_images
        self.save_clicked = False
        self.goto_urls = []

    def locator(self, selector):
        if selector == uploader.MAIN_IMAGE_SELECTOR:
            return FakeLocator([self.main])
        if selector == uploader.GALLERY_IMAGE_SELECTOR:
            # كل استدعاء يرجّع الحقول التي لم تُستخدم بعد (كما بالصفحة الحقيقية).
            return FakeLocator([e for e in self.gallery if e.files == 0])
        if selector == uploader.SEARCH_INPUT_SELECTOR:
            return FakeLocator([FakeElement()])
        if "remove-image" in selector:
            return FakeLocator([FakeElement() for _ in range(self.old_images)])
        return FakeLocator([])

    def goto(self, url, **kwargs):
        self.goto_urls.append(url)
        self.url = url

    def wait_for_selector(self, selector, **kwargs):
        if self.locator(selector).count() == 0:
            raise TimeoutError(f"{selector} not found")

    def wait_for_timeout(self, ms):
        pass

    def wait_for_url(self, pattern, **kwargs):
        return True

    def get_by_role(self, *args, **kwargs):
        page = self

        class Button:
            def click(self):
                page.save_clicked = True

        return Button()


# ---------------------------------------------------------
# العيب ١ — رفع جزئي كان يُبلَّغ كنجاح كامل
# ---------------------------------------------------------

def test_full_upload_still_succeeds():
    """الحالة السليمة لم تتغيّر: كل الصور تُرفع ويُضغط 'اعتماد'."""
    page = FakePage(gallery_slots=5)
    result = uploader.upload_product_images(
        page, page.url, "1.png", [f"{i}.png" for i in range(2, 7)], dry_run=False,
    )
    assert result.success is True
    assert result.images_uploaded == 6
    assert page.save_clicked is True


def test_missing_gallery_fields_no_longer_report_success():
    """
    العيب المُثبَت: حقول المعرض غير موجودة ⇒ تُرفع الرئيسية وحدها، وكانت النتيجة
    "تم الرفع والحفظ بنجاح" مع ضغط 'اعتماد' ونقل المجلد لـ_uploaded.
    """
    page = FakePage(gallery_slots=0)
    result = uploader.upload_product_images(
        page, page.url, "1.png", [f"{i}.png" for i in range(2, 7)], dry_run=False,
    )
    assert result.success is False
    assert "رفع ناقص" in result.message
    assert "1 من 6" in result.message
    assert page.save_clicked is False, "ما كان يجب ضغط 'اعتماد' برفع ناقص"


def test_partially_available_gallery_fields_fail_too():
    """رفع 3 من 6 فشل أيضاً - أي نقص يوقف الاعتماد، لا الصفر فقط."""
    page = FakePage(gallery_slots=2)
    result = uploader.upload_product_images(
        page, page.url, "1.png", [f"{i}.png" for i in range(2, 7)], dry_run=False,
    )
    assert result.success is False
    assert "3 من 6" in result.message
    assert page.save_clicked is False


def test_a_main_image_field_that_rejects_the_file_is_detected():
    """الصورة الرئيسية كانت تُحتسب مرفوعة دائماً بلا أي تحقق."""
    page = FakePage(gallery_slots=5, main_accepts=False)
    result = uploader.upload_product_images(
        page, page.url, "1.png", [f"{i}.png" for i in range(2, 7)], dry_run=False,
    )
    assert result.success is False
    assert "5 من 6" in result.message
    assert page.save_clicked is False


def test_partial_upload_is_not_retried():
    """الرفع الناقص ليس خطأ شبكة عابراً - إعادة المحاولة كانت سترفع الصور مرتين."""
    page = FakePage(gallery_slots=0)
    uploader.upload_product_images(page, page.url, "1.png", ["2.png"], dry_run=False)
    assert page.goto_urls.count(page.url) <= 1


def test_dry_run_never_saves_even_on_a_complete_upload():
    page = FakePage(gallery_slots=5)
    result = uploader.upload_product_images(
        page, page.url, "1.png", [f"{i}.png" for i in range(2, 7)], dry_run=True,
    )
    assert result.success is True
    assert page.save_clicked is False


# ---------------------------------------------------------
# التحقق من جلسة المتجر (بدل افتراضها)
# ---------------------------------------------------------

def test_a_valid_session_passes():
    page = FakePage()
    ok, error = uploader.verify_store_session(page)
    assert ok is True and error == ""


def test_a_redirect_to_the_login_page_is_detected():
    page = FakePage()
    original_goto = page.goto

    def goto(url, **kwargs):
        original_goto(url, **kwargs)
        page.url = "https://admin.sooqifyonline.com/login"

    page.goto = goto
    ok, error = uploader.verify_store_session(page)
    assert ok is False
    assert "منتهية" in error


def test_a_missing_search_field_is_treated_as_no_session():
    class NoSearch(FakePage):
        def locator(self, selector):
            if selector == uploader.SEARCH_INPUT_SELECTOR:
                return FakeLocator([])
            return super().locator(selector)

    ok, error = uploader.verify_store_session(NoSearch())
    assert ok is False
    assert "حقل البحث" in error


# ---------------------------------------------------------
# العيب ٢ — الأرشفة كانت تحذف أرشيفاً سابقاً بنفس الاسم
# ---------------------------------------------------------

def _relocator(tmp_path):
    """يبني Api بلا نافذة ولا سجل حقيقي، لاختبار النقل وحده."""
    import logging
    import main as app_main

    api = app_main.Api.__new__(app_main.Api)
    api.logger = logging.getLogger("test_relocate")
    api._window = None
    return api, app_main


def _make_product(root, *parts):
    folder = os.path.join(root, *parts)
    os.makedirs(folder)
    with open(os.path.join(folder, "1.png"), "wb") as handle:
        handle.write(("/".join(parts)).encode("utf-8"))
    return folder


def test_same_named_folders_from_two_brands_both_survive(tmp_path):
    """
    العيب المُثبَت: BrandA/A1 و BrandB/A1 كانا ينتهيان لنفس الوجهة، فتُحذف صور
    BrandA نهائياً بـrmtree والسجل يقول "تم النقل بنجاح".
    """
    api, _ = _relocator(tmp_path)
    root = os.path.join(str(tmp_path), "images")
    first = _make_product(root, "BrandA", "2026-09-01", "A1")
    second = _make_product(root, "BrandB", "2026-09-01", "A1")

    assert api._relocate_product(first, root, True) is True
    assert api._relocate_product(second, root, True) is True

    archive = os.path.join(str(tmp_path), "images_uploaded")
    kept = {}
    for current, _dirs, files in os.walk(archive):
        for name in files:
            with open(os.path.join(current, name), "rb") as handle:
                kept[os.path.relpath(os.path.join(current, name), archive)] = handle.read().decode()

    assert len(kept) == 2, f"ضاع مجلد بالأرشفة: {kept}"
    assert set(kept.values()) == {"BrandA/2026-09-01/A1", "BrandB/2026-09-01/A1"}


def test_the_archive_mirrors_the_source_tree(tmp_path):
    api, _ = _relocator(tmp_path)
    root = os.path.join(str(tmp_path), "images")
    folder = _make_product(root, "BrandA", "2026-09-01", "A1")
    api._relocate_product(folder, root, True)
    expected = os.path.join(str(tmp_path), "images_uploaded", "BrandA", "2026-09-01", "A1", "1.png")
    assert os.path.isfile(expected)


def test_a_true_collision_adds_a_suffix_and_deletes_nothing(tmp_path):
    """حتى لو تصادم المسار الكامل، لا يُحذف شيء - تُضاف لاحقة."""
    api, _ = _relocator(tmp_path)
    root = os.path.join(str(tmp_path), "images")
    folder = _make_product(root, "A1")

    # نزرع أرشيفاً سابقاً بنفس المسار بالضبط
    existing = os.path.join(str(tmp_path), "images_uploaded", "A1")
    os.makedirs(existing)
    with open(os.path.join(existing, "old.png"), "wb") as handle:
        handle.write(b"previous")

    api._relocate_product(folder, root, True)
    assert os.path.isfile(os.path.join(existing, "old.png")), "الأرشيف السابق حُذف!"
    assert os.path.isfile(os.path.join(str(tmp_path), "images_uploaded", "A1_2", "1.png"))


def test_a_path_outside_the_root_is_refused(tmp_path):
    api, _ = _relocator(tmp_path)
    root = os.path.join(str(tmp_path), "images")
    os.makedirs(root)
    outside = _make_product(str(tmp_path), "elsewhere", "A1")
    assert api._relocate_product(outside, root, False, "أي خطأ") is False
    assert os.path.isfile(os.path.join(outside, "1.png")), "مجلد خارج الجذر تحرّك!"


@pytest.mark.parametrize("message,expected", [
    ("رفع ناقص: رُفعت 1 من 6 صورة", "رفع_ناقص"),
    ("غير موجود بالمتجر: لا نتائج", "غير_موجود_في_المتجر"),
    ("فشل التحقق: معرّف المنتج المحلي '9' غير مطابق للعلامات", "عدم_تطابق_الهوية"),
    ("فشل الرفع: يوجد صور سابقة تمنع الرفع الجديد", "صور_قديمة_تمنع_الرفع"),
    ("الحفظ لم يُؤكَّد", "فشل_حفظ_التعديلات"),
    ("شيء غريب", "أخطاء_أخرى"),
])
def test_failure_categories(message, expected, tmp_path):
    api, _ = _relocator(tmp_path)
    assert api._classify_failure(message) == expected


def test_failed_products_land_under_their_category(tmp_path):
    api, _ = _relocator(tmp_path)
    root = os.path.join(str(tmp_path), "images")
    folder = _make_product(root, "BrandA", "A1")
    api._relocate_product(folder, root, False, "رفع ناقص: رُفعت 1 من 6 صورة")
    expected = os.path.join(str(tmp_path), "images_failed", "رفع_ناقص", "BrandA", "A1", "1.png")
    assert os.path.isfile(expected)


# ---------------------------------------------------------
# كتابة الإعدادات الذرّية
# ---------------------------------------------------------

def test_config_round_trips(isolated_config_dir):
    saved = app_config.save_config({"RootFolder": "D:/images", "OperatorName": "معتز"})
    assert saved["RootFolder"] == "D:/images"
    assert app_config.load_config()["OperatorName"] == "معتز"


def test_config_write_leaves_no_temp_files(isolated_config_dir):
    app_config.save_config({"RootFolder": "D:/images"})
    leftovers = [n for n in os.listdir(isolated_config_dir) if n.endswith(".tmp")]
    assert not leftovers, f"ملفات مؤقتة متروكة: {leftovers}"


def test_a_crash_mid_write_never_truncates_the_existing_config(isolated_config_dir, monkeypatch):
    """
    الضمانة الحقيقية للكتابة الذرّية: الحفظ السابق كان يُفرّغ الملف فوراً بوضع "w"،
    فأي انقطاع بعدها يفقد RootFolder و SyncToken معاً بصمت.
    """
    app_config.save_config({"RootFolder": "D:/images", "SyncToken": "SECRET"})

    real_replace = os.replace

    def exploding_replace(src, dst):
        raise OSError("انقطاع أثناء الاستبدال")

    monkeypatch.setattr(os, "replace", exploding_replace)
    with pytest.raises(OSError):
        app_config.save_config({"RootFolder": "D:/other"})
    monkeypatch.setattr(os, "replace", real_replace)

    survived = app_config.load_config()
    assert survived["RootFolder"] == "D:/images"
    assert survived["SyncToken"] == "SECRET"
    assert not [n for n in os.listdir(isolated_config_dir) if n.endswith(".tmp")]


def test_a_non_string_operator_name_does_not_break_saving(isolated_config_dir):
    """`.strip()` على قيمة غير نصية كان يرمي AttributeError ويُسقط الحفظ كاملاً."""
    saved = app_config.save_config({"OperatorName": 12345, "RootFolder": "D:/x"})
    assert saved["DeveloperMode"] is False
    assert app_config.load_config()["RootFolder"] == "D:/x"


def test_the_developer_trigger_still_works(isolated_config_dir):
    assert app_config.save_config({"OperatorName": "Yousef"})["DeveloperMode"] is True
    assert app_config.save_config({"OperatorName": "معتز"})["DeveloperMode"] is False


def test_a_corrupt_config_file_falls_back_without_crashing(isolated_config_dir):
    with open(app_config.get_config_path(), "w", encoding="utf-8") as handle:
        handle.write("{broken")
    assert app_config.load_config()["RootFolder"] == ""


# ---------------------------------------------------------
# حارس المسارات
# ---------------------------------------------------------

def test_is_inside_guards_against_escaping_the_root(tmp_path):
    import main as app_main

    root = os.path.join(str(tmp_path), "images")
    assert app_main._is_inside(os.path.join(root, "A1"), root) is True
    assert app_main._is_inside(os.path.join(root, "..", "elsewhere"), root) is False
    assert app_main._is_inside("", root) is False
