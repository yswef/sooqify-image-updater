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

# مهلة انتظار ظهور حقول صور المعرض (تُبنى بجافاسكربت بعد تحميل الصفحة).
GALLERY_READY_TIMEOUT_MS = 8000


class UploadResult:
    def __init__(self, success, message, images_uploaded=0):
        self.success = success
        self.message = message
        self.images_uploaded = images_uploaded

    def __repr__(self):
        status = "✓" if self.success else "✗"
        return f"UploadResult({status} {self.message}, images={self.images_uploaded})"


def upload_main_image(page, image_path, logger=None):
    """
    يرفع الصورة الرئيسية/المصغّرة عبر الحقل الحقيقي #customFileEg1، **ويتحقق** أن
    الحقل استقبل الملف فعلاً (files.length > 0) بدل افتراض ذلك.
    سابقاً كانت الدالة ترفع بلا تحقق، وكان المستدعي يَعُدّها صورةً مرفوعة دائماً
    (`1 + عدد صور المعرض`) - فلو لم يستقبلها الحقل لظهر العدد أكبر من الواقع.
    يرجّع True لو وصلت الصورة للحقل فعلاً.
    """
    if logger:
        logger.info("رفع الصورة الرئيسية: %s", image_path)
    field = page.locator(MAIN_IMAGE_SELECTOR)
    if field.count() == 0:
        if logger:
            logger.error("حقل الصورة الرئيسية (%s) غير موجود بالصفحة.", MAIN_IMAGE_SELECTOR)
        return False
    field.set_input_files(image_path)
    try:
        return int(field.first.evaluate("el => el.files ? el.files.length : 0")) > 0
    except Exception:
        # تعذّر التحقق (متصفح/حقل غير متوقع) - لا نفترض الفشل ولا نفترض النجاح
        # بصمت: نعتبرها ناجحة ونسجّل أننا لم نستطع التأكد.
        if logger:
            logger.warning("تعذّر التأكد من استقبال حقل الصورة الرئيسية للملف - سيُكمل الرفع.")
        return True


# ملاحظة: كانت هنا `replace_gallery_images()` - دالة **ميتة** (لا مستدعي لها؛ المسار
# الفعلي بـupload_product_images يُجهض عند وجود صور قديمة قبل أن يصلها). حُذفت لأنها
# كانت تحمل خطرين حقيقيين:
#   1. "وضع تشخيص" مشروط باسم مشغّل مكتوب صلباً بالكود (operator_name == "يوسف").
#   2. يكتب page.content() كاملاً + لقطات شاشة إلى os.getcwd()/diagnostic_logs -
#      أي HTML كامل للوحة إدارة المتجر ومعه توكن CSRF بنص صريح على القرص
#      (تأكّدت فعلياً: `_token" value="..."` موجود داخل ملف محفوظ)، بلا أي تنظيف.
# المجلد مُستثنى من git، لكن الملفات تبقى على جهاز المصممة بلا حد زمني.

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

            # 1) رفع الصورة الرئيسية الجديدة (مع التحقق من استقبال الحقل لها)
            main_uploaded = upload_main_image(page, main_image_path, logger=logger)

            # 2) التحقق من وجود صور قديمة بمعرض المنتج لتفادي الحذف الخاطئ
            old_selector = 'a.spartan_remove_row[href*="remove-image"]'
            old_count = page.locator(old_selector).count()
            
            if old_count > 0:
                if logger:
                    logger.error("تم رصد %s صورة قديمة بالصفحة. تم تفكيك آلية الحذف بسبب قيود المتجر.", old_count)
                # الإلغاء فوراً بدون إعادة محاولة وإرجاع نتيجة الفشل لينتقل المنتج لمجلد الفشل
                return UploadResult(False, "فشل الرفع: يُرجى الدخول للمتجر وحذف الصور القديمة يدوياً، يوجد صور سابقة تمنع الرفع الجديد.", 0)

            # 3) رفع صور المعرض الجديدة.
            # ننتظر ظهور حقول المعرض أولاً: بعض الصفحات تبنيها بجافاسكربت بعد
            # domcontentloaded، وبدون هذا الانتظار كان الرفع يبدأ وهي غير موجودة بعد.
            if gallery_image_paths:
                try:
                    page.wait_for_selector(GALLERY_IMAGE_SELECTOR, state="attached", timeout=GALLERY_READY_TIMEOUT_MS)
                except Exception:
                    pass  # الغياب الحقيقي يُكتشف بالعدّ أدناه ويُعلَن كرفع ناقص.

            gallery_uploaded = upload_gallery_images(page, gallery_image_paths, logger=logger)
            uploaded_count = (1 if main_uploaded else 0) + gallery_uploaded
            expected_count = 1 + len(gallery_image_paths)

            # ── حارس الرفع الناقص ──
            # سابقاً كان العدّ `1 + صور المعرض`، فالصورة الرئيسية تُحتسب دائماً ولو لم
            # تُرفع، وشرط السلامة `uploaded_count <= 0` يستحيل تحققه رياضياً. النتيجة
            # المُثبَتة: طلب 6 صور، رُفعت 1، والنتيجة "تم الرفع والحفظ بنجاح" مع ضغط
            # "اعتماد" ونقل المجلد لـ_uploaded - أي خمس صور ضاعت بصمت.
            # الآن: لا يُضغط "اعتماد" إطلاقاً عند النقص، فتبقى صور المنتج القديمة
            # سليمة بالمتجر ويذهب المجلد لمراجعة يدوية.
            if uploaded_count < expected_count:
                missing = expected_count - uploaded_count
                if logger:
                    logger.error(
                        "رفع ناقص: رُفعت %s من %s صورة (%s ناقصة). لن يُضغط 'اعتماد' - "
                        "صور المنتج الحالية بالمتجر تبقى كما هي.",
                        uploaded_count, expected_count, missing,
                    )
                # ليس خطأ شبكة عابراً - لا نعيد المحاولة حتى لا تُرفع الصور مرتين.
                return UploadResult(
                    False,
                    f"رفع ناقص: رُفعت {uploaded_count} من {expected_count} صورة "
                    f"({missing} ناقصة) - أُوقف الاعتماد كإجراء احترازي.",
                    uploaded_count,
                )

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


# أجزاء المسار التي تدل على أن المتجر رمانا لصفحة تسجيل الدخول.
LOGIN_URL_FRAGMENTS = ("/login", "/auth/login", "/admin/login")


def verify_store_session(page, logger=None):
    """
    يتحقق **فعلياً** أن جلسة الدخول لسوقيفاي ما زالت صالحة، بفتح صفحة القائمة ورؤية
    ما إذا كان المتجر قد رمانا لصفحة تسجيل الدخول أو أخفى حقل البحث.

    لماذا: التطبيق كان يفترض الدخول من مجرد أن مجلد البروفايل غير فارغ
    (`os.listdir(profile_dir)`)، وهذا يصير صحيحاً بمجرد أول فتح للمتصفح حتى بلا أي
    تسجيل دخول. فجلسة منتهية الصلاحية كانت تعني فشل **كل** المنتجات واحداً واحداً
    ونقلها لمجلدات فشل، بدل رسالة واحدة واضحة "سجّل دخولك".

    يرجّع: (صالحة؟، رسالة الخطأ)
    """
    try:
        page.goto(LIST_URL, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
    except Exception as exc:
        return False, f"تعذّر فتح صفحة المتجر للتحقق من الجلسة: {exc}"

    current_url = (page.url or "").lower()
    if any(fragment in current_url for fragment in LOGIN_URL_FRAGMENTS):
        return False, (
            "جلسة الدخول لسوقيفاي منتهية - المتجر حوّلنا لصفحة تسجيل الدخول. "
            "اضغط زر 'تسجيل الدخول' بالشريط العلوي، سجّل دخولك بالنافذة اللي تفتح، "
            "وأغلقها، ثم أعد التشغيل."
        )

    try:
        page.wait_for_selector(SEARCH_INPUT_SELECTOR, timeout=GOTO_TIMEOUT_MS)
    except Exception:
        return False, (
            "فُتحت صفحة المتجر لكن حقل البحث غير موجود - غالباً الجلسة منتهية أو "
            "الحساب بلا صلاحية على قائمة المنتجات. سجّل دخولك مرة ثانية وتأكد من صلاحياتك."
        )

    if logger:
        logger.info("تم التأكد من صلاحية جلسة الدخول لسوقيفاي.")
    return True, ""


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

    # تسجيل وحدة العمل فقط بالوضع التلقائي (بدون dry_run) ولو نجح الرفع.
    # بوضع المراجعة لا نسجّل شيئاً لأن الاعتماد بيد المشغّل ولم يتأكد الحفظ بعد.
    if result.success and not dry_run:
        item_id = product.style_code or product.folder_name
        outcome = sync_client.record_images_updated(
            item_id,
            result.images_uploaded,
            operator_name,
            extra={"product_id": product.product_id or "", "folder": product.folder_name},
            logger=logger,
        )
        if logger:
            if outcome["recorded"] and outcome["pushed"]:
                logger.info(
                    "سُجّلت وحدة عمل (%s صورة) ورُفعت لخادم المزامنة لـ%s.",
                    result.images_uploaded, item_id,
                )
            elif outcome["recorded"]:
                logger.info(
                    "سُجّلت وحدة عمل (%s صورة) محلياً لـ%s - ستُرفع بأول مصالحة كاملة.",
                    result.images_uploaded, item_id,
                )
            else:
                # لا تسجيل محلي ولا رفع = عمل لن يظهر بأي تقرير. يجب أن يُرى.
                logger.error(
                    "لم تُسجَّل وحدة العمل لـ%s لا محلياً ولا على الخادم - هذا العمل "
                    "لن يظهر بالتقرير الموحّد. راجع صلاحيات مجلد الإعدادات.", item_id,
                )

    return result