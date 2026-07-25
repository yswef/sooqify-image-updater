# =========================================================
# Sooqify Image Updater
# التواصل مع sync.php نفسه (نفس نظام AlphaCode) - حل هوية المنتج من كود الستايل،
# وتسجيل كل عملية رفع صور ناجحة (تظهر لاحقاً بتقرير AlphaCode).
# =========================================================
# تطوير: يوسف الحمزي

import datetime
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

    def report_upload(self, product_key, images_uploaded, operator_name, product_id=None, logger=None):
        """
        يسجّل عملية رفع صور ناجحة - يظهر لاحقاً بتقرير AlphaCode كقسم "الصور المعدَّلة".
        تفاصيل التاريخ ومعرّف المنتج الإضافي تُرفق لإنتاج إحصائيات دقيقة.
        """
        if not self.configured:
            if logger:
                logger.warning(
                    "لم يُسجَّل عدد الصور بتقرير المزامنة لـ %s - المزامنة غير مُفعّلة/معدّة بالإعدادات.",
                    product_key,
                )
            return False
        
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data, error = self._call("push", {
            "key": f"IMAGE_UPDATE_{product_key}",
            "product": {
                "event": "image_update",
                "product_key": product_key,
                "product_id": product_id,  # إضافة معرّف الحساب المحلي للتقرير
                "images_uploaded": images_uploaded,
                "updated_by": operator_name,
                "upload_time": now_str
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

    def report_batch_summary(self, operator_name, success_count, failed_count, skipped_count, total_images, logger=None):
        """
        يُرسل تقريراً إجمالياً بملخص عملية الرفع الحالية (عدد المجلدات الكاملة، الناجحة، الفاشلة، المتخطاة والصور المرفوعة)
        لمطابقتها ومعرفة إنتاجية الموظف في لوحة المزامنة المركزية.
        """
        if not self.configured:
            return False
        
        now_dt = datetime.datetime.now()
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        key_str = f"BATCH_SUM_{operator_name}_{now_dt.strftime('%H-%M-%S')}"
        
        payload = {
            "key": key_str,
            "product": {
                "event": "batch_run_summary",
                "operator": operator_name,
                "success_count": success_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
                "total_images_uploaded": total_images,
                "completed_at": now_str
            }
        }
        data, error = self._call("push", payload, method="POST")
        if error:
            if logger:
                logger.warning("فشل إرسال إجمالي ملخص الرفع لخادم المزامنة: %s", error)
            return False
        if logger:
            logger.info("تم إرسال تقرير ملخص إجمالي العملية بنجاح لخادم المزامنة (%s).", key_str)
        return True