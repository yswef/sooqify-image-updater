# =========================================================
# Sooqify Image Updater
# فحص المجلد الرئيسي، قراءة كل مجلد منتج وملف product_info.txt، وترتيب الصور
# بحيث تكون 1.png هي الرئيسية دائماً.
# =========================================================
# تطوير: يوسف الحمزي

import os
import re
from dataclasses import dataclass, field

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# على القرص توجد **صيغتان** لملف بيانات المنتج، وكلتاهما حقيقيتان:
#
#   product_info.txt  (مجلدات المصممة)      : Name ×2 + Style Code + Date Added + Added By
#                                             — بلا Product ID
#   style_code.txt    (مُخرَج AlphaCode الحالي): Style Code + Search Code + Product ID
#                                             — بلا أسماء ولا Added By
#
# قبل هذا التغيير كان السكانر يقرأ الأول فقط، فأي مجلد قادم من AlphaCode مباشرةً
# ينتهي بـstyle_code فارغ وname_en فارغ ⇒ has_search_key=False ⇒ **يُتخطّى بصمت**.
# تُحقق منه على بيانات حقيقية: 80 مجلداً بصيغة style_code.txt على هذا الجهاز كانت
# ستُتخطّى بالكامل. نقرأ الاثنين ونضمّهما، فيكمل كلٌّ نقص الآخر.
INFO_FILENAMES = ("product_info.txt", "style_code.txt")

# متروك للتوافق الخلفي مع أي مستدعٍ خارجي قديم.
INFO_FILENAME = INFO_FILENAMES[0]

# يطابق أسطر product_info.txt الحالية: "Style Code: XXXX", وأيضاً "Product ID: 123"
# لو أُعيد إضافته لاحقاً بالتطبيق الرئيسي (متوافق للأمام بدون أي تعديل هنا).
INFO_LINE_PATTERN = re.compile(r"^\s*([A-Za-z ]+)\s*:\s*(.*)$")


@dataclass
class ProductFolder:
    path: str
    folder_name: str
    style_code: str = ""
    search_code: str = ""         # رقم بحث المورّد - موجود بـstyle_code.txt وحده.
    product_id: str = ""          # موجود بـstyle_code.txt؛ product_info.txt لا يحمله.
    name_en: str = ""
    name_ar: str = ""
    added_by: str = ""
    date_added: str = ""
    images: list = field(default_factory=list)   # مرتّبة: [الرئيسية, فرعية...]
    info_found: bool = False

    @property
    def has_search_key(self):
        """أي مفتاح بحث نقدر نستخدمه بلوحة سوقيفاي - الستايل كود أو كود البحث أو الاسم."""
        return bool(self.style_code or self.search_code or self.name_en)


def parse_product_info(info_path):
    """
    يقرأ product_info.txt ويرجّع (القيم كقاموس، قائمة أسطر "Name" بترتيبها الأصلي).
    قراءة واحدة للملف تكفي للاثنين: سابقاً كان الملف يُفتح مرة ثانية داخل list
    comprehension بـscan_product_folder بلا with ولا close - مقبض ملف مسرَّب لكل
    منتج، وبفحص آلاف المجلدات قد يصطدم بحد المقابض المفتوحة بالنظام، وعلى ويندوز
    يبقى الملف مقفولاً فيفشل نقل مجلد المنتج بعد الرفع.
    """
    values = {}
    name_lines = []
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            for line in f:
                match = INFO_LINE_PATTERN.match(line)
                if not match:
                    continue
                key = match.group(1).strip().lower()
                value = match.group(2).strip()
                if value == "-":
                    value = ""
                if key == "name":
                    name_lines.append(value)
                values[key] = value
    except OSError:
        pass
    return values, name_lines


def sort_images(image_filenames):
    """
    يرتّب الصور بحيث "1.xxx" دائماً أولاً (الصورة الرئيسية)، والباقي رقمياً بعدها.
    أي اسم غير رقمي يُرحَّل لنهاية القائمة بدل ما يكسر الترتيب.
    """
    def sort_key(filename):
        stem = os.path.splitext(filename)[0]
        return (0, int(stem)) if stem.isdigit() else (1, filename.lower())

    return sorted(image_filenames, key=sort_key)


def scan_product_folder(folder_path):
    """يبني ProductFolder من مجلد منتج واحد، أو None لو المجلد لا يحتوي أي صور أصلاً."""
    folder_name = os.path.basename(folder_path.rstrip(os.sep))
    try:
        entries = os.listdir(folder_path)
    except OSError:
        return None

    image_files = [
        name for name in entries
        if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS
    ]
    if not image_files:
        return None

    product = ProductFolder(
        path=folder_path,
        folder_name=folder_name,
        images=sort_images(image_files),
    )

    # نضمّ كل ملفات البيانات الموجودة. أول قيمة غير فارغة تفوز، فلا يمحو ملفٌ
    # لاحق قيمةً صحيحة قرأها سابقه.
    merged = {}
    all_name_lines = []
    for filename in INFO_FILENAMES:
        info_path = os.path.join(folder_path, filename)
        if not os.path.isfile(info_path):
            continue
        values, name_lines = parse_product_info(info_path)
        product.info_found = True
        for key, value in values.items():
            if value and not merged.get(key):
                merged[key] = value
        all_name_lines.extend(name for name in name_lines if name)

    if product.info_found:
        product.style_code = merged.get("style code", "")
        product.search_code = merged.get("search code", "")
        product.product_id = merged.get("product id", "")
        product.added_by = merged.get("added by", "")
        product.date_added = merged.get("date added", "")
        # أول سطرين "Name:" هما الإنجليزي ثم العربي بنفس ترتيب كتابتهما بالملف الأصلي.
        if all_name_lines:
            product.name_en = all_name_lines[0]
        if len(all_name_lines) > 1:
            product.name_ar = all_name_lines[1]

    return product


def scan_root_folder(root_folder, progress_callback=None):
    """
    يمسح كل المجلدات الفرعية المباشرة تحت المجلد الرئيسي (بأي عمق تنظيم - براند/تاريخ/منتج)،
    ويرجّع كل مجلد فيه صور كـ ProductFolder واحد.
    تتخطي الدالة مجلدات الرفع والأرشفة الناجحة أو الفاشلة.
    """
    products = []
    for current_dir, sub_dirs, _files in os.walk(root_folder):
        # تعديل sub_dirs في الموضع (in-place) يمنع os.walk من الدخول إليها
        sub_dirs[:] = [
            d for d in sub_dirs
            if not d.lower().endswith("_uploaded") and not d.lower().endswith("_failed")
        ]
        
        curr_name = os.path.basename(current_dir).lower()
        if curr_name.endswith("_uploaded") or curr_name.endswith("_failed"):
            continue
            
        product = scan_product_folder(current_dir)
        if product:
            products.append(product)
            if progress_callback:
                progress_callback(product.folder_name, len(products))
    return products


# =========================================================
# ملاحظة (مُحدَّثة بعد التحقق من الملفات الفعلية على القرص):
# الملاحظة السابقة هنا كانت تقول إن "Product ID" أُزيل من التطبيق الرئيسي وإن التحقق
# من الهوية معطَّل عملياً. الواقع أدق: AlphaCode **ما زال يكتبه**، لكن في ملف آخر
# اسمه style_code.txt (راجع backend/app/api/routes/upload_routes.py سطر 589)، بينما
# مجلدات المصممة القديمة تحمل product_info.txt بلا هذا السطر.
# الآن نقرأ الملفين معاً، فمتى توفّر Product ID عمل التحقق من العلامات (Tags) فعلياً
# عبر uploader.verify_product_tags، ومتى غاب عاد السلوك للبحث بالستايل كود/الاسم
# كما كان - بلا تعطّل ولا تحقق كاذب.
# =========================================================
