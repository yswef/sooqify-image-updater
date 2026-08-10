# =========================================================
# Sooqify Image Updater
# أتمتة رفع الصور + البحث الآمن والتحقق من هوية المنتج - كل المحددات (selectors)
# مستخرجة من HTML فعلي (صفحات التعديل، القائمة، والعرض)، لا تخمين.
# =========================================================
# تطوير: يوسف الحمزي

import os
import time

# ---------------------------------------------------------
# رفع الصور (صفحة التعديل)
# ---------------------------------------------------------

MAIN_IMAGE_SELECTOR = "#customFileEg1"
GALLERY_IMAGE_SELECTOR = "input.spartan_image_input"
SAVE_BUTTON_TEXT = "اعتماد"
LIST_PAGE_URL_FRAGMENT = "/admin/item/list"

# مهلة تنقّل صريحة (مليثانية). نستخدم "domcontentloaded" بدل "networkidle" لأن لوحات
# التحكم غالباً فيها اتصالات خلفية مستمرة (تنبيهات/تحديث لحظي) خلي الصفحة أبداً توصل
# "idle" فعلياً بشبكتها، وهذا كان يسبب تعليق طويل بصمت بدون أي خطأ واضح.
GOTO_TIMEOUT_MS = 20000


class UploadResult:
    def __init__(self, success, message, images_uploaded=0):
        self.success = success
        self.message = message
        self.images_uploaded = images_uploaded

    def __repr__(self):
        status = "✓" if self.success else "✗"
        return f"UploadResult({status} {self.message}, images={self.images_uploaded})"


def upload_main_image(page, image_path, logger=None):
    """يرفع الصورة الرئيسية/المصغّرة عبر الحقل الحقيقي #customFileEg1."""
    if logger:
        logger.info("رفع الصورة الرئيسية: %s", image_path)
    page.locator(MAIN_IMAGE_SELECTOR).set_input_files(image_path)


def upload_gallery_images(page, image_paths, logger=None):
    """
    يرفع صور المعرض واحدة تلو الأخرى عبر حقول SpartanMultiImagePicker.
    كل صورة تُختار، حقل جديد فاضٍ يظهر تلقائياً (data-spartanindexinput أعلى) -
    لذلك نعيد البحث عن آخر حقل فاضٍ قبل كل صورة بدل الاعتماد على فهرس ثابت.
    """
    uploaded = 0
    for image_path in image_paths:
        gallery_inputs = page.locator(GALLERY_IMAGE_SELECTOR)
        count = gallery_inputs.count()
        if count == 0:
            if logger:
                logger.warning("ما فيه حقل صورة معرض فاضٍ متاح - توقف الرفع عند %s صورة.", uploaded)
            break
        last_input = gallery_inputs.nth(count - 1)  # آخر حقل بالصفحة هو الفاضي دائماً.
        last_input.set_input_files(image_path)
        uploaded += 1
        if logger:
            logger.info("  [%s/%s] رُفعت صورة معرض: %s", uploaded, len(image_paths), image_path)
        page.wait_for_timeout(300)  # مهلة قصيرة تعطي السكربت وقت يضيف الحقل الجديد.
    return uploaded


def save_product_form(page, timeout_ms=30000, logger=None):
    """يضغط زر "اعتماد" وينتظر التوجيه الحقيقي لصفحة القائمة (دليل نجاح الحفظ المؤكَّد)."""
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


def upload_product_images(page, edit_url, main_image_path, gallery_image_paths, logger=None):
    """يفتح صفحة التعديل (لو لسه ما مفتوحة)، يرفع الصور بالترتيب، يحفظ، ويتحقق من نجاح الحفظ."""
    try:
        if page.url != edit_url:
            if logger:
                logger.info("جارِ فتح صفحة التعديل: %s", edit_url)
            page.goto(edit_url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
            page.wait_for_selector(MAIN_IMAGE_SELECTOR, state="attached", timeout=GOTO_TIMEOUT_MS)

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
# البحث الآمن + التحقق من الهوية (صفحتا القائمة والعرض)
# ---------------------------------------------------------

LIST_URL = "https://admin.sooqifyonline.com/admin/item/list"
SEARCH_INPUT_SELECTOR = "#datatableSearch"
ROW_SELECTOR = "table tbody tr"
VIEW_EDIT_BUTTON_SELECTOR = 'a.btn.btn--primary[href*="/item/edit/"]'


class SearchResult:
    def __init__(self, found, edit_url=None, message="", matched_id=None):
        self.found = found
        self.edit_url = edit_url
        self.message = message
        self.matched_id = matched_id

    def __repr__(self):
        status = "✓" if self.found else "✗"
        return f"SearchResult({status} {self.message}, edit_url={self.edit_url})"


def search_and_open_product(page, style_code_or_name, logger=None):
    """
    يبحث عن منتج بكود الستايل (أو الاسم) بصفحة القائمة، ويفتح صفحة العرض لأول نتيجة
    مطابقة مباشرة - بدون أي تحقق من الـ ID مقابل نظام المزامنة (بناءً على طلب المستخدم:
    البحث بالكود كافٍ، والتحقق الإضافي مو مطلوب).
    """
    if logger:
        logger.info("بحث عن: %s", style_code_or_name)

    started = time.monotonic()
    page.goto(LIST_URL, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
    page.wait_for_selector(SEARCH_INPUT_SELECTOR, timeout=GOTO_TIMEOUT_MS)
    if logger:
        logger.info("تم تحميل صفحة القائمة خلال %.1f ثانية.", time.monotonic() - started)

    page.fill(SEARCH_INPUT_SELECTOR, style_code_or_name)
    page.wait_for_timeout(700)  # DataTables تفلتر محلياً - مهلة قصيرة كافية بدل انتظار شبكة.

    rows = page.locator(ROW_SELECTOR)
    row_count = rows.count()
    if row_count == 0:
        return SearchResult(False, message=f"لا نتائج بحث لـ '{style_code_or_name}' بالمتجر.")

    if row_count > 1 and logger:
        logger.warning(
            "%s نتيجة مطابقة لـ '%s' - سيُستخدم أول نتيجة (بدون تحقق ID حسب الإعداد الحالي).",
            row_count, style_code_or_name,
        )

    view_href = rows.first.locator('a[href*="/item/view/"]').first.get_attribute("href")
    if not view_href:
        return SearchResult(False, message="نتيجة بحث موجودة لكن بدون رابط عرض صالح.")

    page.goto(view_href, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
    edit_link = page.locator(VIEW_EDIT_BUTTON_SELECTOR).first
    edit_url = edit_link.get_attribute("href")
    if not edit_url:
        return SearchResult(False, message="ما لقيت رابط تعديل بصفحة عرض المنتج.")

    if logger:
        logger.info("تم العثور على المنتج -> %s", edit_url)
    return SearchResult(True, edit_url=edit_url, message="تم العثور على المنتج.")


# ---------------------------------------------------------
# خط الأنابيب الكامل لمنتج واحد
# ---------------------------------------------------------

def process_product_folder(page, sync_client, product, operator_name, logger=None):
    """
    1) يبحث عن المنتج بلوحة سوقيفاي بكود الستايل مباشرة (بدون أي تحقق من ID مقابل نظام المزامنة).
    2) يرفع الصور (الأولى رئيسية، الباقي معرض) ويحفظ.
    3) يسجّل عدد الصور المرفوعة بنظام المزامنة (يظهر لاحقاً بتقرير AlphaCode) - أفضل جهد،
       ما يوقف العملية لو فشل التسجيل لأن الرفع نفسه سبق ونجح فعلياً بالمتجر.
    """
    if not product.style_code:
        return UploadResult(False, "المنتج بلا كود ستايل - ما فيه شي أبحث فيه بالمتجر.")

    try:
        search_result = search_and_open_product(page, product.style_code, logger=logger)
    except Exception as exc:
        if logger:
            logger.error("فشل البحث بصفحة سوقيفاي: %s", exc)
        return UploadResult(False, f"خطأ أثناء البحث: {exc}")

    if not search_result.found:
        return UploadResult(False, search_result.message)

    images = [os.path.join(product.path, name) for name in product.images]
    result = upload_product_images(page, search_result.edit_url, images[0], images[1:], logger=logger)

    if result.success:
        reported = sync_client.report_upload(product.style_code, result.images_uploaded, operator_name, logger=logger)
        if reported and logger:
            logger.info("تم تسجيل %s صورة بتقرير المزامنة لـ %s.", result.images_uploaded, product.style_code)

    return result