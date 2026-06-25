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
INFO_FILENAME = "product_info.txt"

# يطابق أسطر product_info.txt الحالية: "Style Code: XXXX", وأيضاً "Product ID: 123"
# لو أُعيد إضافته لاحقاً بالتطبيق الرئيسي (متوافق للأمام بدون أي تعديل هنا).
INFO_LINE_PATTERN = re.compile(r"^\s*([A-Za-z ]+)\s*:\s*(.*)$")


@dataclass
class ProductFolder:
    path: str
    folder_name: str
    style_code: str = ""
    product_id: str = ""          # قد يبقى فارغاً لو الملف القديم بلا هذا السطر - راجع الملاحظة بالأسفل.
    name_en: str = ""
    name_ar: str = ""
    added_by: str = ""
    date_added: str = ""
    images: list = field(default_factory=list)   # مرتّبة: [الرئيسية, فرعية...]
    info_found: bool = False

    @property
    def has_search_key(self):
        """أي مفتاح بحث نقدر نستخدمه بلوحة سوقيفاي - الستايل كود أو الاسم."""
        return bool(self.style_code or self.name_en)


def parse_product_info(info_path):
    """يقرأ product_info.txt ويرجّع القيم كقاموس بسيط، بلا حساسية لترتيب الأسطر."""
    values = {}
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
                values[key] = value
    except OSError:
        pass
    return values


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

    info_path = os.path.join(folder_path, INFO_FILENAME)
    if os.path.isfile(info_path):
        values = parse_product_info(info_path)
        product.info_found = True
        product.style_code = values.get("style code", "")
        product.product_id = values.get("product id", "")
        product.added_by = values.get("added by", "")
        product.date_added = values.get("date added", "")
        # أول سطرين "Name:" هما الإنجليزي ثم العربي بنفس ترتيب كتابتهما بالملف الأصلي.
        name_lines = [
            match.group(2).strip()
            for line in open(info_path, "r", encoding="utf-8")
            if (match := INFO_LINE_PATTERN.match(line)) and match.group(1).strip().lower() == "name"
        ]
        if name_lines:
            product.name_en = name_lines[0]
        if len(name_lines) > 1:
            product.name_ar = name_lines[1]

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
# ملاحظة مهمة: عمود "Product ID" غير موجود بالنسخة الحالية من product_info.txt
# (أُزيل بتحديث سابق بالتطبيق الرئيسي). التحقق الآمن من هوية المنتج قبل التعديل
# يحتاج هذا الرقم مطابقاً للعلامة (Tag) المكتوبة يدوياً بلوحة سوقيفاي. يوصى بإعادة
# سطر "Product ID: {next_id}" لدالة كتابة product_info.txt بـ app.py قبل تفعيل
# خطوة التحقق فعلياً - بدون هذا السطر، يعمل هذا الملف بالبحث بالستايل كود/الاسم
# فقط دون تحقق إضافي من رقم الـ ID.
# =========================================================