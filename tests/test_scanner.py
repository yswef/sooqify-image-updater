# =========================================================
# Sooqify Image Updater - اختبارات فحص المجلدات
# يحرس تحديداً إصلاح مقبض الملف المسرَّب: قراءة واحدة تعطي القيم وأسطر الاسم معاً.
# =========================================================

import gc
import os
import warnings

import scanner

INFO = """Style Code: SC-100
Name: Leather Sneaker
Name: حذاء جلد
Added By: معتز
Date Added: 2026-09-20
Product ID: 4512
"""


def _make_product(tmp_path, name="A1", info=INFO, images=("2.png", "1.png", "10.png")):
    folder = tmp_path / name
    folder.mkdir(parents=True)
    for image in images:
        (folder / image).write_bytes(b"x")
    if info is not None:
        (folder / "product_info.txt").write_text(info, encoding="utf-8")
    return folder


def test_info_is_parsed_in_a_single_read(tmp_path):
    folder = _make_product(tmp_path)
    values, name_lines = scanner.parse_product_info(str(folder / "product_info.txt"))
    assert values["style code"] == "SC-100"
    assert values["added by"] == "معتز"
    assert values["product id"] == "4512"
    # ترتيب أسطر "Name" محفوظ: الإنجليزي أولاً ثم العربي.
    assert name_lines == ["Leather Sneaker", "حذاء جلد"]


def test_scanning_leaks_no_open_file_handle(tmp_path):
    """
    العيب المُصلَح: الملف كان يُفتح مرة ثانية داخل list comprehension بلا with ولا
    close، فيترك مقبضاً مفتوحاً لكل منتج. ResourceWarning هنا هو الدليل القاطع.
    """
    _make_product(tmp_path, "A1")
    _make_product(tmp_path, "A2")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        products = scanner.scan_root_folder(str(tmp_path))
        gc.collect()
    assert len(products) == 2
    leaks = [w for w in caught if issubclass(w.category, ResourceWarning)]
    assert not leaks, f"تسريب مقبض ملف أثناء الفحص: {[str(w.message) for w in leaks]}"


def test_product_fields_are_populated(tmp_path):
    folder = _make_product(tmp_path)
    product = scanner.scan_product_folder(str(folder))
    assert product.style_code == "SC-100"
    assert product.name_en == "Leather Sneaker"
    assert product.name_ar == "حذاء جلد"
    assert product.added_by == "معتز"
    assert product.product_id == "4512"
    assert product.info_found is True
    assert product.has_search_key is True


def test_main_image_sorts_first_and_numbers_sort_numerically(tmp_path):
    folder = _make_product(tmp_path, images=("2.png", "1.png", "10.png", "cover.png"))
    product = scanner.scan_product_folder(str(folder))
    assert product.images == ["1.png", "2.png", "10.png", "cover.png"]


def test_folder_without_images_is_not_a_product(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    (folder / "product_info.txt").write_text(INFO, encoding="utf-8")
    assert scanner.scan_product_folder(str(folder)) is None


def test_missing_info_file_still_yields_a_product(tmp_path):
    folder = _make_product(tmp_path, info=None)
    product = scanner.scan_product_folder(str(folder))
    assert product is not None
    assert product.info_found is False
    assert product.style_code == ""


def test_archive_folders_are_skipped(tmp_path):
    _make_product(tmp_path, "live")
    _make_product(tmp_path, os.path.join("images_uploaded", "done"))
    _make_product(tmp_path, os.path.join("images_failed", "broken"))
    names = {p.folder_name for p in scanner.scan_root_folder(str(tmp_path))}
    assert names == {"live"}
