# =========================================================
# Sooqify Image Updater
# التواصل مع sync.php نفسه (نفس نظام AlphaCode) - حل هوية المنتج من كود الستايل،
# وتسجيل كل عملية رفع صور ناجحة (تظهر لاحقاً بتقرير AlphaCode).
# =========================================================
# تطوير: يوسف الحمزي

import requests

REQUEST_TIMEOUT = (5, 10)  # (اتصال, قراءة) بالثواني - قصيرة حتى ما تعلّق الواجهة.


class SyncClient:
    def __init__(self, server_url, token):
        self.server_url = (server_url or "").rstrip("/")
        self.token = token or ""

    @property
    def configured(self):
        return bool(self.server_url and self.token)

    def _call(self, action, payload=None, method="POST"):
        if not self.configured:
            return None, "sync_not_configured"
        url = f"{self.server_url}/sync.php"
        headers = {"X-Sync-Token": self.token, "Content-Type": "application/json"}
        try:
            if method == "GET":
                response = requests.get(url, params={"action": action}, headers=headers, timeout=REQUEST_TIMEOUT)
            else:
                response = requests.post(url, params={"action": action}, headers=headers, json=payload or {}, timeout=REQUEST_TIMEOUT)
            data = response.json()
            if response.status_code >= 400:
                return data, data.get("error") or f"HTTP {response.status_code}"
            return data, None
        except requests.RequestException as exc:
            return None, str(exc)
        except ValueError as exc:
            return None, f"استجابة غير صالحة من خادم المزامنة: {exc}"

    def lookup_product_by_style_code(self, style_code):
        """
        يبحث عن منتج بكود الستايل بنظام المزامنة المركزي ويرجّع بياناته (فيها id الحقيقي)،
        بدل الاعتماد على أي رقم مخزّن محلياً بملف نصي.
        يرجّع: (product_dict أو None, رسالة خطأ أو None)
        """
        if not style_code:
            return None, "لا يوجد كود ستايل لهذا المنتج."
        data, error = self._call("lookup", {"key": style_code}, method="POST")
        if error:
            return None, error
        if data and data.get("success"):
            return data.get("product"), None
        return None, "لم يُعثر على المنتج بنظام المزامنة."

    def report_upload(self, product_key, images_uploaded, operator_name, logger=None):
        """
        يسجّل عملية رفع صور ناجحة - يظهر لاحقاً بتقرير AlphaCode كقسم "الصور المعدَّلة".
        لا يوقف العمل لو فشل (الرفع نفسه سبق ونجح فعلياً بالمتجر)، لكن يسجّل تحذيراً واضحاً
        بالسجل لو فشل - خصوصاً "Unauthorized" اللي معناها SyncToken هنا ما يطابق $SECRET_TOKEN
        بملف sync.php على السيرفر.
        """
        if not self.configured:
            if logger:
                logger.warning(
                    "لم يُسجَّل عدد الصور بتقرير المزامنة لـ %s - المزامنة غير مُفعّلة/معدّة بالإعدادات.",
                    product_key,
                )
            return False
        data, error = self._call("push", {
            "key": f"IMAGE_UPDATE_{product_key}",
            "product": {
                "event": "image_update",
                "product_key": product_key,
                "images_uploaded": images_uploaded,
                "updated_by": operator_name,
            },
        }, method="POST")
        if error:
            if logger:
                logger.warning(
                    "الرفع نجح لكن فشل تسجيله بتقرير المزامنة لـ %s: %s"
                    + (" (تأكد إن SyncToken بالإعدادات يطابق التوكن بملف sync.php على السيرفر بالضبط)"
                       if error == "Unauthorized" else ""),
                    product_key, error,
                )
            return False
        return True