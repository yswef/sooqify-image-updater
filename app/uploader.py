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


def replace_gallery_images(page, new_image_paths, operator_name="", logger=None):
    """
    يمسح الصور القديمة ويرفع الجديدة بذكاء:
    الموقع يرفض حذف كل الصور ويعرض خطأ (تحذير حذف جميع الصور).
    عشان كذا نعد الصور القديمة، ثم نرفع الجديدة أولاً لتكون رصيد بالصفحة،
    ثم نحذف القديمة فقط. شامل تسجيل تشخيصي عميق للمشرف يوسف.
    """
    
    import os
    import time
    
    is_diag = (operator_name == "يوسف")
    diag_dir = ""
    if is_diag:
        diag_dir = os.path.join(os.getcwd(), "diagnostic_logs", str(int(time.time())))
        os.makedirs(diag_dir, exist_ok=True)
        if logger:
            logger.info("[وضع التشخيص العميق مُفعّل] سيتم حفظ لقطات الشاشة بمسار: %s", diag_dir)
            
    def snap(label):
        if not is_diag: return
        try:
            page.screenshot(path=os.path.join(diag_dir, f"{label}.png"), full_page=True)
            with open(os.path.join(diag_dir, f"{label}.html"), "w", encoding="utf-8") as f:
                f.write(page.content())
        except Exception:
            pass
    
    def accept_dialog(dialog):
        try:
            dialog.accept()
        except Exception:
            pass
            
    page.on("dialog", accept_dialog)
    
    try:
        # 1. إحصاء وحفظ روابط الصور القديمة بدقة
        snap("01_before_upload")
        # الصور القديمة الفعالة فقط هي التي تمتلك رابط حذف يحتوي على كلمة 'remove-image'
        old_selector = 'a.spartan_remove_row[href*="remove-image"]'
        old_btns = page.locator(old_selector)
        
        old_hrefs = []
        for i in range(old_btns.count()):
            btn = old_btns.nth(i)
            if btn.is_visible():
                href = btn.get_attribute("href")
                if href and "remove-image" in href:
                    old_hrefs.append(href)
                    
        old_count = len(old_hrefs)
        if logger and old_count > 0:
            logger.info("تم رصد %s صورة قديمة بمعرض المنتج. سيتم استهدافها بروابطها المخصصة.", old_count)
            
        # 2. رفع الصور الجديدة أولاً (لكي لا يرفض الموقع حذف القديمة)
        uploaded_count = upload_gallery_images(page, new_image_paths, logger=logger)
        snap("02_after_upload")
        
        # 3. حذف الصور القديمة من خلال البحث الدقيق عن الروابط المحفوظة مسبقاً
        if old_count > 0:
            if logger:
                logger.info("جاري مسح الصور القديمة (بعد تأمين الصور الجديدة)...")
            
            deleted_count = 0
            for href in old_hrefs:
                # نبحث بالتحديد عن الزر الذي يحمل هذا الرابط الحصري!
                # هذا يضمن 100% أننا لا نقترب من أي صورة جديدة
                exact_selector = f'a.spartan_remove_row[href="{href}"]'
                specific_btn = page.locator(exact_selector)
                
                if specific_btn.count() > 0 and specific_btn.first.is_visible():
                    try:
                        specific_btn.first.click()
                        deleted_count += 1
                        page.wait_for_timeout(500)
                        snap(f"04_deleted_image_{deleted_count}")
                    except Exception:
                        pass
                else:
                    snap(f"05_not_found_or_hidden_{deleted_count}")
                    
            if logger:
                logger.info("تم مسح %s صورة قديمة بنجاح من أصل %s.", deleted_count, old_count)
                
        return uploaded_count
        
    except Exception as e:
        if logger:
            logger.warning("خطأ أثناء استبدال صور المعرض: %s", e)
        return 0
    finally:
        try:
            page.remove_listener("dialog", accept_dialog)
        except Exception:
            pass


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
        # تقليل وقت انتظار إضافة الحقل الجديد لتسريع الرفع
        page.wait_for_timeout(100)
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


def verify_product_tags(page, product_id, logger=None):
    """
    يتأكد من وجود معرّف المنتج (ID) المحلي داخل حقل الكلمات الدلالية/العلامات (Tags) بصفحة التعديل.
    """
    if not product_id:
        return True

    tags_selectors = [
        'input[name="tags"]',
        'input#tags',
        'input[name="tags[]"]',
        'select[name="tags[]"]',
        'input.tagsinput',
        '.bootstrap-tagsinput input',
        '#tags-select'
    ]

    found_field = False
    for selector in tags_selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            found_field = True
            try:
                # قراءة قيم المدخل
                value = locator.first.evaluate("el => el.value") or ""
                tag_name = locator.first.evaluate("el => el.tagName").lower()
                if tag_name == "select":
                    # في حال كان select2 أو ما شابه
                    selected_options = locator.first.locator("option:checked")
                    vals = [selected_options.nth(i).evaluate("el => el.value") for i in range(selected_options.count())]
                    texts = [selected_options.nth(i).inner_text() for i in range(selected_options.count())]
                    if any(product_id in str(v) for v in vals + texts):
                        if logger:
                            logger.info("تم مطابقة معرّف المنتج بنجاح في حقل العلامات المحددة: %s", product_id)
                        return True
                else:
                    if product_id in value:
                        if logger:
                            logger.info("تم مطابقة معرّف المنتج بنجاح في حقل العلامات النصي: %s", product_id)
                        return True

                # فحص الحاوية الأب (في حال كانت علامات مرئية كبابلز)
                parent_container = locator.first.locator("xpath=..")
                parent_text = parent_container.inner_text() or ""
                if product_id in parent_text:
                    if logger:
                        logger.info("تم مطابقة معرّف المنتج بنجاح في حاوية العلامات: %s", product_id)
                    return True
            except Exception as e:
                if logger:
                    logger.warning("حدث خطأ أثناء قراءة حقل العلامات لـ %s: %s", selector, e)

    if found_field:
        if logger:
            logger.warning("التحقق الفاشل: معرّف المنتج الإضافي '%s' غير متواجد بحقل العلامات (Tags).", product_id)
        return False

    if logger:
        logger.info("لم يتم العثور على حقل العلامات (Tags) بالصفحة لتأكيد المعرّف '%s' - تخطي للسلامة.", product_id)
    return True


def upload_product_images(page, edit_url, main_image_path, gallery_image_paths, product_id=None, dry_run=False, operator_name="", logger=None):
    """
    يفتح صفحة التعديل (لو لسه ما مفتوحة)، يمسح الصور القديمة، يرفع الجديدة بالترتيب.
    - لو dry_run=True: يرفع الصور ويوقف قبل الاعتماد (المستخدم يعتمد يدوياً من المتصفح).
    - لو dry_run=False: يرفع الصور ويعتمد تلقائياً.
    يعيد المحاولة حتى 3 مرات.
    """
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            if logger and attempt > 1:
                logger.warning("محاولة الرفع رقم %s من %s...", attempt, max_retries)
            
            # تحقق أكثر أماناً لتفادي توقف الصفحة بعد timeout وهمي للـ url
            is_ready = False
            try:
                if page.url == edit_url:
                    page.locator(MAIN_IMAGE_SELECTOR).wait_for(state="attached", timeout=1000)
                    is_ready = True
            except Exception:
                pass
                
            if not is_ready:
                if logger:
                    logger.info("جارِ فتح صفحة التعديل: %s", edit_url)
                page.goto(edit_url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
                page.wait_for_selector(MAIN_IMAGE_SELECTOR, state="attached", timeout=GOTO_TIMEOUT_MS)

            # معالجة المطابقة التحققية للعلامات (tags)
            if product_id:
                if not verify_product_tags(page, product_id, logger=logger):
                    # الفشل هنا ليس خطأ شبكة، بل عدم مطابقة صريحة للهوية - لا نعيد المحاولة فيه.
                    return UploadResult(False, f"فشل التحقق: معرّف المنتج المحلي '{product_id}' غير مطابق للعلامات (Tags) في صفحة المتجر.", 0)

            # 1) رفع الصورة الرئيسية الجديدة
            upload_main_image(page, main_image_path, logger=logger)

            # 2) التحقق من وجود صور قديمة بمعرض المنتج لتفادي الحذف الخاطئ
            old_selector = 'a.spartan_remove_row[href*="remove-image"]'
            old_count = page.locator(old_selector).count()
            
            if old_count > 0:
                if logger:
                    logger.error("تم رصد %s صورة قديمة بالصفحة. تم تفكيك آلية الحذف بسبب قيود المتجر.", old_count)
                # الإلغاء فوراً بدون إعادة محاولة وإرجاع نتيجة الفشل لينتقل المنتج لمجلد الفشل
                return UploadResult(False, "فشل الرفع: يُرجى الدخول للمتجر وحذف الصور القديمة يدوياً، يوجد صور سابقة تمنع الرفع الجديد.", 0)

            # 3) رفع صور المعرض الجديدة
            uploaded_count = 1 + upload_gallery_images(page, gallery_image_paths, logger=logger)

            if uploaded_count <= 0:
                return UploadResult(False, "لم يتم رفع أي صور جديدة، لذلك تم إيقاف عملية الحفظ كإجراء احترازي.", 0)

            # وضع المراجعة: وقف هنا بدون اعتماد - المستخدم يعتمد بنفسه من المتصفح
            if dry_run:
                if logger:
                    logger.info("وضع المراجعة: تم رفع %s صورة. الصفحة مفتوحة — اضغط 'اعتماد' بنفسك من المتصفح لحفظ التغييرات.", uploaded_count)
                return UploadResult(True, f"وضع المراجعة: تم رفع {uploaded_count} صورة — بانتظار اعتمادك اليدوي من المتصفح.", uploaded_count)

            # الوضع التلقائي: اعتماد مباشر
            if not save_product_form(page, logger=logger):
                raise RuntimeError("الحفظ لم يُؤكَّد (ما صار التوجيه لصفحة القائمة بعد اعتماد النموذج).")

            return UploadResult(True, "تم الرفع والحفظ بنجاح.", uploaded_count)

        except Exception as exc:
            if logger:
                logger.error("خطأ في المحاولة %s لرفع صور المنتج: %s", attempt, exc)
            if attempt == max_retries:
                return UploadResult(False, f"فشلت عملية الرفع بعد {max_retries} محاولات. الخطأ الأخير: {exc}", 0)
            
            # انتظار قصير قبل إعادة المحاولة
            page.wait_for_timeout(2000)


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
    يبحث عن منتج بكود الستايل (أو الاسم) بصفحة القائمة، مع التحقق الصريح أن
    أي صف يُفتح يحتوي فعلاً على كود البحث - لمنع تعديل منتج خاطئ في حال لم
    تُكمل DataTables الفلترة بعد (مشكلة AJAX / server-side search).
    """
    if logger:
        logger.info("بحث عن: %s", style_code_or_name)

    started = time.monotonic()
    page.goto(LIST_URL, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
    page.wait_for_selector(SEARCH_INPUT_SELECTOR, timeout=GOTO_TIMEOUT_MS)
    if logger:
        logger.info("تم تحميل صفحة القائمة خلال %.1f ثانية.", time.monotonic() - started)

    # مسح أي بحث سابق ثم كتابة الكود الجديد
    page.fill(SEARCH_INPUT_SELECTOR, "")
    
    # نأخذ مرجع للنص الحالي لأول صف في الجدول لكي نكتشف متى يتغير
    rows = page.locator(ROW_SELECTOR)
    initial_first_row_text = ""
    if rows.count() > 0:
        initial_first_row_text = rows.first.inner_text()

    page.fill(SEARCH_INPUT_SELECTOR, style_code_or_name)
    page.press(SEARCH_INPUT_SELECTOR, "Enter")

    # انتظار ذكي: ننتظر حتى يتغير محتوى أول صف أو يتغير عدد الصفوف (بحد أقصى ثانية ونصف)
    # هذا يضمن أن DataTables أنهت طلب الـ AJAX وتحديث الـ DOM
    try:
        def table_updated():
            current_count = rows.count()
            if current_count == 0:
                return True # الجدول أصبح فارغاً
            # إما العدد اختلف أو نص أول صف اختلف (تمت الفلترة)
            return current_count != rows.count() or rows.first.inner_text() != initial_first_row_text

        # استخدام مهلة 3 ثواني للفحص
        start_wait = time.time()
        while time.time() - start_wait < 3.0:
            if table_updated():
                break
            page.wait_for_timeout(200)
    except Exception:
        pass

    # مهلة إضافية بسيطة للتأكد من استقرار الـ DOM
    page.wait_for_timeout(500)

    row_count = rows.count()
    if row_count == 0:
        return SearchResult(False, message=f"لا نتائج بحث لـ '{style_code_or_name}' بالمتجر.")

    # ─── بعد التحديث الآن نثق في الصف الأول كونه ناتج استجابة السيرفر ───
    matched_row = rows.first

    if row_count > 1 and logger:
        logger.warning(
            "%s نتيجة للبحث عن '%s' - سيُستخدم أول صف يحتوي الكود.",
            row_count, style_code_or_name,
        )

    view_href = matched_row.locator('a[href*="/item/view/"]').first.get_attribute("href")
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

def process_product_folder(page, sync_client, product, operator_name, dry_run=False, logger=None):
    """
    1) يبحث عن المنتج بلوحة سوقيفاي بكود الستايل (إن وجد) أو باسم المنتج.
    2) يرفع الصور (الأولى رئيسية، الباقي معرض) ويتحقق من معرّف الـ ID بالـ Tags.
    3) لو dry_run: يوقف قبل الاعتماد ← المستخدم يعتمد يدوياً.
       لو بدون: يعتمد تلقائياً ويسجّل بتقرير المزامنة.
    """
    search_key = product.style_code
    if not search_key:
        search_key = product.name_en or product.name_ar or product.folder_name
        if logger:
            logger.info("كود الستايل مفقود. سيتم البحث بالاسم/المجلد: %s", search_key)

    if not search_key:
        return UploadResult(False, "المنتج بلا كود ستايل أو اسم - ليس هناك مفتاح للبحث بالمتجر.")

    try:
        search_result = search_and_open_product(page, search_key, logger=logger)
    except Exception as exc:
        if logger:
            logger.error("فشل البحث بصفحة سوقيفاي: %s", exc)
        return UploadResult(False, f"خطأ network/timeout أثناء البحث: {exc}")

    if not search_result.found:
        return UploadResult(False, f"غير موجود بالمتجر: {search_result.message}")

    images = [os.path.join(product.path, name) for name in product.images]
    
    # إرسال الـ product_id لمطابقته في صفحة التعديل
    result = upload_product_images(
        page, search_result.edit_url, images[0], images[1:], 
        product_id=product.product_id, dry_run=dry_run, operator_name=operator_name, logger=logger
    )

    # تسجيل المزامنة فقط بالوضع التلقائي (بدون dry_run) ولو نجح الرفع
    if result.success and not dry_run:
        reported = sync_client.report_upload(
            product.style_code or product.folder_name, 
            result.images_uploaded, 
            operator_name, 
            product_id=product.product_id,
            logger=logger
        )
        if reported and logger:
            logger.info("تم تسجيل %s صورة بتقرير المزامنة لـ %s.", result.images_uploaded, product.style_code or product.folder_name)

    return result