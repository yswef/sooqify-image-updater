# =========================================================
# Sooqify Image Updater
# Image-upload automation + safe search and product-identity verification - every
# selector below was extracted from real HTML (edit, list, and view pages), not guessed.
# =========================================================
# Developer: Yousef Alhamzy

from __future__ import annotations

import os
import time
from typing import Any

# ---------------------------------------------------------
# Image upload (edit page)
# ---------------------------------------------------------

MAIN_IMAGE_SELECTOR = "#customFileEg1"
GALLERY_IMAGE_SELECTOR = "input.spartan_image_input"
SAVE_BUTTON_TEXT = "اعتماد"
LIST_PAGE_URL_FRAGMENT = "/admin/item/list"

# Explicit navigation timeout (ms). We use "domcontentloaded" instead of "networkidle"
# because admin dashboards usually keep some background connection alive (live
# notifications/polling), which would keep the page from ever reaching network "idle" -
# that used to cause a long silent hang with no clear error.
GOTO_TIMEOUT_MS = 20000


class UploadResult:
    def __init__(self, success: bool, message: str, images_uploaded: int = 0) -> None:
        self.success = success
        self.message = message
        self.images_uploaded = images_uploaded

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"UploadResult({status} {self.message}, images={self.images_uploaded})"


def upload_main_image(page: Any, image_path: str, logger: Any = None) -> None:
    """Uploads the main/thumbnail image via the real #customFileEg1 field."""
    if logger:
        logger.info("رفع الصورة الرئيسية: %s", image_path)
    page.locator(MAIN_IMAGE_SELECTOR).set_input_files(image_path)


def upload_gallery_images(page: Any, image_paths: list[str], logger: Any = None) -> int:
    """
    Uploads gallery images one at a time via SpartanMultiImagePicker fields.
    Each time an image is picked, a new empty field appears automatically
    (data-spartanindexinput above) - so we re-look-up the last empty field before each
    image instead of relying on a fixed index.
    """
    uploaded = 0
    for image_path in image_paths:
        gallery_inputs = page.locator(GALLERY_IMAGE_SELECTOR)
        count = gallery_inputs.count()
        if count == 0:
            if logger:
                logger.warning("ما فيه حقل صورة معرض فاضٍ متاح - توقف الرفع عند %s صورة.", uploaded)
            break
        last_input = gallery_inputs.nth(count - 1)  # The last field on the page is always the empty one.
        last_input.set_input_files(image_path)
        uploaded += 1
        if logger:
            logger.info("  [%s/%s] رُفعت صورة معرض: %s", uploaded, len(image_paths), image_path)
        page.wait_for_timeout(300)  # Brief pause to give the page script time to add the new field.
    return uploaded


def save_product_form(page: Any, timeout_ms: int = 30000, logger: Any = None) -> bool:
    """Clicks the save button and waits for the actual redirect to the list page (confirmed proof the save succeeded)."""
    if logger:
        logger.info("جارِ الضغط على زر الحفظ...")
    page.get_by_role("button", name=SAVE_BUTTON_TEXT, exact=True).click()
    try:
        page.wait_for_url(f"**{LIST_PAGE_URL_FRAGMENT}**", timeout=timeout_ms)
        return True
    except Exception as exc:
        if logger:
            logger.error("لم يحدث التوجيه المتوقع لصفحة القائمة خلال %sms: %s", timeout_ms, exc)
        return False


def upload_product_images(
    page: Any, edit_url: str, main_image_path: str, gallery_image_paths: list[str], logger: Any = None
) -> UploadResult:
    """Opens the edit page (if not already open), uploads images in order, saves, and confirms the save succeeded."""
    try:
        if page.url != edit_url:
            if logger:
                logger.info("جارِ فتح صفحة التعديل: %s", edit_url)
            page.goto(edit_url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
            page.wait_for_selector(MAIN_IMAGE_SELECTOR, timeout=GOTO_TIMEOUT_MS)

        upload_main_image(page, main_image_path, logger=logger)
        uploaded_count = 1 + upload_gallery_images(page, gallery_image_paths, logger=logger)

        if not save_product_form(page, logger=logger):
            return UploadResult(False, "الحفظ لم يُؤكَّد (ما صار التوجيه المتوقع لصفحة القائمة).", uploaded_count)

        return UploadResult(True, "تم الرفع والحفظ بنجاح.", uploaded_count)

    except Exception as exc:
        if logger:
            logger.error("فشل رفع صور المنتج: %s", exc)
        return UploadResult(False, f"خطأ غير متوقع: {exc}", 0)


# ---------------------------------------------------------
# Safe search + identity verification (list and view pages)
# ---------------------------------------------------------

LIST_URL = "https://admin.sooqifyonline.com/admin/item/list"
SEARCH_INPUT_SELECTOR = "#datatableSearch"
ROW_SELECTOR = "table tbody tr"
VIEW_EDIT_BUTTON_SELECTOR = 'a.btn.btn--primary[href*="/item/edit/"]'


class SearchResult:
    def __init__(
        self, found: bool, edit_url: str | None = None, message: str = "", matched_id: Any = None
    ) -> None:
        self.found = found
        self.edit_url = edit_url
        self.message = message
        self.matched_id = matched_id

    def __repr__(self) -> str:
        status = "✓" if self.found else "✗"
        return f"SearchResult({status} {self.message}, edit_url={self.edit_url})"


def _read_tags_column(page: Any) -> str:
    """
    Reads the "Tags" column from the price/variants details table on the view page, by
    actually searching for the column header instead of assuming it's always the last
    column (safer if the column order ever changes).
    """
    headers = page.locator("table thead th")
    tags_index = None
    for i in range(headers.count()):
        if "العلامات" in headers.nth(i).inner_text():
            tags_index = i
            break
    if tags_index is None:
        return ""
    first_row_cells = page.locator(ROW_SELECTOR).first.locator("td")
    if tags_index >= first_row_cells.count():
        return ""
    return first_row_cells.nth(tags_index).inner_text().strip()


def search_and_open_product(
    page: Any, style_code_or_name: str, expected_id: Any, logger: Any = None
) -> SearchResult:
    """
    Searches for a product by style code (or name) on the list page, opens the view page
    for each result, checks the real ID matches (the "Tags" column), and returns the edit
    URL only on a confirmed match - never guesses or proceeds without a match.

    expected_id: the expected number from the sync system (sync_client.lookup_product_by_style_code).
    """
    if logger:
        logger.info("بحث عن: %s (المتوقع ID=%s)", style_code_or_name, expected_id)

    started = time.monotonic()
    page.goto(LIST_URL, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
    page.wait_for_selector(SEARCH_INPUT_SELECTOR, timeout=GOTO_TIMEOUT_MS)
    if logger:
        logger.info("تم تحميل صفحة القائمة خلال %.1f ثانية.", time.monotonic() - started)

    page.fill(SEARCH_INPUT_SELECTOR, style_code_or_name)
    page.wait_for_timeout(700)  # DataTables filters client-side - a short pause is enough, no need to wait on the network.

    rows = page.locator(ROW_SELECTOR)
    row_count = rows.count()
    if row_count == 0:
        return SearchResult(False, message=f"لا نتائج بحث لـ '{style_code_or_name}'.")

    view_links = []
    for i in range(row_count):
        href = rows.nth(i).locator('a[href*="/item/view/"]').first.get_attribute("href")
        if href:
            view_links.append(href)

    if not view_links:
        return SearchResult(False, message="نتائج بحث موجودة لكن بدون رابط عرض صالح.")
    if len(view_links) > 1 and logger:
        logger.warning("%s نتيجة مطابقة - سيتم التحقق من كل واحدة للعثور على الـ ID الصحيح.", len(view_links))

    for view_url in view_links:
        page.goto(view_url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
        page.wait_for_selector("table thead th", timeout=GOTO_TIMEOUT_MS)
        tags_text = _read_tags_column(page)

        if str(expected_id) in [t.strip() for t in tags_text.split(",")]:
            edit_link = page.locator(VIEW_EDIT_BUTTON_SELECTOR).first
            edit_url = edit_link.get_attribute("href")
            if logger:
                logger.info("تطابق مؤكد! ID=%s -> %s", expected_id, edit_url)
            return SearchResult(True, edit_url=edit_url, message="تطابق مؤكد.", matched_id=expected_id)

        if logger:
            logger.info("  تجاوز نتيجة: العلامات = '%s' لا تطابق المتوقع %s", tags_text, expected_id)

    return SearchResult(
        False,
        message=f"وُجدت {len(view_links)} نتيجة لكن ولا واحدة منها علاماتها تطابق ID={expected_id} - "
                f"يحتاج مراجعة يدوية، تم التخطي بأمان.",
    )


# ---------------------------------------------------------
# Full pipeline for a single product
# ---------------------------------------------------------

def process_product_folder(
    page: Any, sync_client: Any, product: Any, operator_name: str, logger: Any = None
) -> UploadResult:
    """
    1) Asks the sync system for the real ID from the style code.
    2) Safely searches for and verifies the product's identity on the Sooqify dashboard.
    3) Uploads the images (first one is main, the rest are gallery) and saves.
    4) Logs success to the sync system (shows up later in the AlphaCode report).
    Never modifies a product without a confirmed ID match - skips and logs the reason instead of guessing.
    """
    if not product.style_code:
        return UploadResult(False, "المنتج بلا كود ستايل - لا يمكن التحقق الآمن، تم التخطي.")

    expected_product, lookup_error = sync_client.lookup_product_by_style_code(product.style_code)
    if lookup_error or not expected_product:
        return UploadResult(False, f"تعذّر معرفة الـ ID من نظام المزامنة: {lookup_error}")

    expected_id = expected_product.get("id")
    try:
        search_result = search_and_open_product(page, product.style_code, expected_id, logger=logger)
    except Exception as exc:
        if logger:
            logger.error("فشل البحث/التحقق بصفحة سوقيفاي: %s", exc)
        return UploadResult(False, f"خطأ أثناء البحث والتحقق: {exc}")

    if not search_result.found:
        return UploadResult(False, f"فشل التحقق الآمن: {search_result.message}")

    images = [os.path.join(product.path, name) for name in product.images]
    result = upload_product_images(page, search_result.edit_url, images[0], images[1:], logger=logger)

    if result.success:
        sync_client.report_upload(product.style_code, result.images_uploaded, operator_name)

    return result