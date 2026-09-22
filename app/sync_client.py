# =========================================================
# Sooqify Image Updater
# التواصل مع sync.php نفسه (نفس بروتوكول AlphaCode حرفياً، بلا بروتوكول ثانٍ):
#     POST ?action=pull   {"since": "<طابع زمني أو نص فارغ>"}   ← فارغ = كل شيء
#     POST ?action=push   {"key": "...", "product": {...}}
#     POST ?action=whoami {"key": ..., "password": ...}
#     ترويسة X-Sync-Token مطلوبة بكل نداء.
#
# ⚠️ لماذا لا يوجد هنا سحب تزايدي بـ"since=آخر سحب" إطلاقاً:
#   بمشروع AlphaCode فقد السحب التزايدي 1324 سجلاً بصمت (3800 على الخادم مقابل 2476
#   محلياً، وشهر كامل من عمل أحد الأعضاء غائب عن كل التقارير) بينما المزامنة تقول
#   "نجحت" وlast_error فارغ - لأن العلامة المائية لمّا تتقدّم فوق دفعة سجلات لا يعود
#   السحب ينظر خلفه أبداً. هنا كل مصالحة **كاملة** (since="")، وتُعلن فارق العدد بين
#   المحلي والبعيد صراحةً بقيمة `delta` بدل ابتلاعه، ولا تُعَدّ ناجحة إلا وdelta = 0.
# =========================================================
# تطوير: يوسف الحمزي

import datetime

import requests

import work_log

REQUEST_TIMEOUT = (5, 10)  # (اتصال, قراءة) بالثواني - قصيرة حتى ما تعلّق الواجهة.

# كل كم ساعة تُجرى مصالحة كاملة تلقائياً. نفس القيمة المستخدمة بـAlphaCode
# (FULL_RECONCILE_INTERVAL_HOURS) حتى لا يتباعد سلوك الطرفين.
FULL_RECONCILE_INTERVAL_HOURS = 6

# تأخير بسيط بين الدفعات المتتالية - الاستضافة المشتركة تحظر (403) عند إغراقها.
# نفس قيمة SYNC_REQUEST_PACING_SECONDS بـAlphaCode.
REQUEST_PACING_SECONDS = 0.3

# حد أعلى لعدد الوحدات المرفوعة بمصالحة واحدة، حتى لا تتحول أول مصالحة على جهاز
# قديم لدفعة آلاف الطلبات تستدعي حظر الاستضافة. الباقي يُرفع بالمصالحة التالية،
# ويبقى معلناً بـ`remaining_to_push` بدل أن يبدو منتهياً.
MAX_PUSH_PER_RECONCILE = 300


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
        url = self.server_url if self.server_url.endswith(".php") else f"{self.server_url}/sync.php"
        headers = {"X-Sync-Token": self.token, "Content-Type": "application/json"}
        try:
            if method == "GET":
                response = requests.get(url, params={"action": action}, headers=headers, timeout=REQUEST_TIMEOUT)
            else:
                response = requests.post(url, params={"action": action}, headers=headers, json=payload or {}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 403:
                # حظر مؤقت من الاستضافة (anti-flood) - نتوقف فوراً بدل إطالة الحظر.
                return None, "sync_blocked_403"
            data = response.json()
            # AlphaCode يرجّع duplicate مع رمز >=400 لدفعٍ مكرر - وهو نجاح لا خطأ.
            if response.status_code >= 400 and not (isinstance(data, dict) and data.get("duplicate")):
                error = (data.get("error") if isinstance(data, dict) else None) or f"HTTP {response.status_code}"
                return data, error
            return data, None
        except requests.RequestException as exc:
            return None, str(exc)
        except ValueError as exc:
            return None, f"استجابة غير صالحة من خادم المزامنة: {exc}"

    # -----------------------------------------------------
    # البروتوكول الأساسي
    # -----------------------------------------------------

    def pull_all(self):
        """
        سحب **كامل** (since="") لكل ما على الخادم. لا يوجد سحب تزايدي بهذا الملف عن قصد
        (اقرأ التحذير بأعلى الملف). يرجّع: (قاموس العناصر، رسالة خطأ أو None).
        """
        data, error = self._call("pull", {"since": ""}, method="POST")
        if error:
            return {}, error
        items = (data or {}).get("items")
        if not isinstance(items, dict):
            # استجابة بلا "items" ليست نجاحاً - لو اعتبرناها قاموساً فارغاً لظهر
            # الخادم "فارغاً" وبدت المزامنة متطابقة وهي لم تقرأ شيئاً أصلاً.
            return {}, "استجابة pull بلا حقل items صالح - لم يُقرأ شيء من الخادم."
        return items, None

    def push_unit(self, unit):
        """يدفع وحدة عمل واحدة بنفس عقد push المستخدم بـAlphaCode. يرجّع: (نجح، خطأ أو None)."""
        key = work_log.work_unit_key(unit)
        data, error = self._call("push", {"key": key, "product": unit}, method="POST")
        if error:
            return False, error
        if isinstance(data, dict) and (data.get("success") or data.get("duplicate")):
            return True, None
        return False, "الخادم لم يؤكد قبول الدفع."

    def resolve_operator_identity(self, operator_name, password="", logger=None):
        """
        يحوّل اسم المشغّل المكتوب محلياً إلى **الاسم القانوني** للعضو كما يعرفه الخادم.

        هذا هو الحل الصحيح لمشكلة ربط الهوية: sync.php يحمل جدولي `members` و
        `member_aliases`، و`whoami` يطابق بالاسم أو بأي اسم مستعار بلا حساسية لحالة
        الأحرف، ويرجّع `display_name`. فبدل تخمين أن "yousef" هي "يوسف" (وهو تخمين
        ممنوع)، نسأل الخادم. تُضاف المرادفات بجدول member_aliases مرة واحدة، فيصير
        الربط بياناتٍ لا استنتاجاً.

        النتيجة تُخزَّن بالحالة المحلية حتى لا يُنادى الخادم مرة لكل منتج.
        فشل التحقق **لا يوقف العمل**: نرجع الاسم المحلي كما هو، ويبقى ربطه ممكناً
        لاحقاً بخريطة التقارير بجهة AlphaCode.
        """
        raw = str(operator_name or "").strip()
        if not raw or not self.configured:
            return raw

        state = work_log.load_sync_state()
        cache = state.get("identity_cache") or {}
        if isinstance(cache, dict) and raw in cache:
            return cache[raw] or raw

        member, error = self.whoami(raw, password)
        canonical = raw
        if member and isinstance(member, dict):
            canonical = str(member.get("display_name") or "").strip() or raw
            if logger and canonical != raw:
                logger.info("رُبط اسم المشغّل '%s' بالعضو '%s' عبر جدول أعضاء الخادم.", raw, canonical)
        elif logger:
            logger.warning(
                "تعذّر التحقق من هوية المشغّل '%s' عبر الخادم (%s) - سيُسجَّل العمل باسمه "
                "المحلي كما هو. لضمّ عمله لنفس الشخص بالتقرير، أضف '%s' كاسم مستعار "
                "بجدول member_aliases، أو اربطه بملف report_identities.json.",
                raw, error, raw,
            )

        cache = dict(cache) if isinstance(cache, dict) else {}
        cache[raw] = canonical
        state["identity_cache"] = cache
        work_log.save_sync_state(state)
        return canonical

    def whoami(self, name, password=""):
        """
        تحقّق الهوية عبر نفس نقطة whoami التي يستخدمها AlphaCode. تُستخدم لربط اسم
        المشغّل المحلي بحساب العضو المركزي بدل الاعتماد على تطابق نصي للأسماء.
        يرجّع: (بيانات العضو أو None، خطأ أو None)
        """
        data, error = self._call("whoami", {"key": name, "password": password}, method="POST")
        if error:
            return None, error
        if isinstance(data, dict) and data.get("success"):
            return data.get("member") or data, None
        return None, (isinstance(data, dict) and data.get("error")) or "تعذّر التحقق من الهوية."

    # -----------------------------------------------------
    # المصالحة الكاملة (الشفاء الذاتي)
    # -----------------------------------------------------

    def reconcile_work_units(self, logger=None):
        """
        مصالحة كاملة بالاتجاهين لوحدات العمل:
          1. سحب كامل (since="") - كل ما على الخادم.
          2. أي وحدة عمل موجودة على الخادم وناقصة محلياً تُضاف للسجل المحلي.
          3. أي وحدة محلية غير موجودة على الخادم تُدفع.
          4. يُعلن **فارق العدد** (delta) صراحةً.

        إضافية بحتة: لا تحذف ولا تستبدل أي وحدة موجودة على أي طرف.
        يرجّع قاموس ملخص. `success` لا تكون True إلا إذا نجح السحب فعلاً؛ و`in_sync`
        لا تكون True إلا وفارق العدد صفر ولا بقي شيء للدفع - فلا يُقال "تمت المزامنة"
        وهناك وحدات ناقصة.
        """
        summary = {
            "success": False, "in_sync": False, "error": None,
            "local_count": 0, "remote_count": 0, "delta": None,
            "pulled_in": 0, "pushed": 0, "push_failed": 0,
            "remaining_to_push": 0, "corrupt_local_lines": 0,
        }
        if not self.configured:
            summary["error"] = "sync_not_configured"
            return summary

        local_units, corrupt = work_log.load_units(logger=logger)
        local_by_key = work_log.units_by_key(local_units)
        summary["local_count"] = len(local_by_key)
        summary["corrupt_local_lines"] = corrupt

        remote_items, error = self.pull_all()
        if error:
            summary["error"] = error
            if logger:
                logger.error("فشلت المصالحة الكاملة لوحدات العمل: %s", error)
            self._store_state(summary)
            return summary
        summary["success"] = True

        # لا نحسب إلا وحدات العمل الخاصة بهذا التطبيق؛ منتجات AlphaCode ليست شغلنا.
        remote_by_key = {
            key: item for key, item in remote_items.items()
            if isinstance(item, dict)
            and item.get(work_log.RECORD_KIND_FIELD) == work_log.RECORD_KIND_WORK_UNIT
            and item.get("source") == work_log.SOURCE_IMAGE_UPDATER
        }
        summary["remote_count"] = len(remote_by_key)
        summary["delta"] = summary["remote_count"] - summary["local_count"]

        # (2) الناقص محلياً يُضاف - هذا هو الشفاء الذاتي: الخادم يُعيد ما فقده الجهاز.
        missing_locally = [key for key in remote_by_key if key not in local_by_key]
        for key in missing_locally:
            if work_log.append_unit(remote_by_key[key], logger=logger):
                summary["pulled_in"] += 1

        # (3) الناقص على الخادم يُدفع، بإيقاع هادئ وحد أعلى للدفعة.
        missing_remotely = [key for key in sorted(local_by_key) if key not in remote_by_key]
        summary["remaining_to_push"] = max(0, len(missing_remotely) - MAX_PUSH_PER_RECONCILE)
        for key in missing_remotely[:MAX_PUSH_PER_RECONCILE]:
            ok, push_error = self.push_unit(local_by_key[key])
            if ok:
                summary["pushed"] += 1
            else:
                summary["push_failed"] += 1
                if logger:
                    logger.warning("فشل دفع وحدة عمل (%s): %s", key, push_error)
                if push_error == "sync_blocked_403":
                    # الاستضافة حظرتنا - نتوقف فوراً ونُعلن الباقي بدل إطالة الحظر.
                    summary["remaining_to_push"] = len(missing_remotely) - summary["pushed"] - summary["push_failed"]
                    break
            _sleep(REQUEST_PACING_SECONDS)

        summary["in_sync"] = (
            summary["delta"] == 0
            and summary["push_failed"] == 0
            and summary["remaining_to_push"] == 0
            and summary["corrupt_local_lines"] == 0
        )

        if logger:
            level = logger.info if summary["in_sync"] else logger.warning
            level(
                "مصالحة وحدات العمل: محلي=%s، خادم=%s، الفارق=%s، أُضيف محلياً=%s، مدفوع=%s، فشل دفع=%s، باقٍ=%s.",
                summary["local_count"], summary["remote_count"], summary["delta"],
                summary["pulled_in"], summary["pushed"], summary["push_failed"],
                summary["remaining_to_push"],
            )
            if not summary["in_sync"]:
                logger.warning(
                    "المزامنة **غير** متطابقة بعد المصالحة - راجع الأرقام أعلاه. "
                    "لا تعتمد على أي تقرير كمكتمل قبل أن يصبح الفارق صفراً."
                )

        self._store_state(summary)
        return summary

    def auto_reconcile_if_due(self, force=False, logger=None):
        """
        يُجري مصالحة كاملة إن مضت FULL_RECONCILE_INTERVAL_HOURS على آخر واحدة (أو force).
        تُستدعى من نهاية كل دفعة تشغيل، فلا يحتاج المشغّل أن يتذكر زراً - وهذا بالضبط
        سبب بقاء فجوة AlphaCode شهراً: دالة المصالحة كانت موجودة لكن لا شيء يستدعيها.
        يرجّع ملخص المصالحة، أو None لو لم يكن موعدها.
        """
        if not self.configured:
            return None
        if not force:
            last_raw = str(work_log.load_sync_state().get("last_reconcile_at") or "")
            if last_raw:
                try:
                    elapsed = datetime.datetime.now() - datetime.datetime.fromisoformat(last_raw)
                    if elapsed < datetime.timedelta(hours=FULL_RECONCILE_INTERVAL_HOURS):
                        return None
                except ValueError:
                    pass  # طابع زمني تالف - نعامله كأنها لم تُجرَ قط ونصالح.
        return self.reconcile_work_units(logger=logger)

    def _store_state(self, summary):
        state = work_log.load_sync_state()
        state["last_reconcile_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        state["last_error"] = summary.get("error") or ""
        state["last_delta"] = summary.get("delta")
        state["last_in_sync"] = summary.get("in_sync")
        work_log.save_sync_state(state)

    # -----------------------------------------------------
    # تسجيل العمل المنجز
    # -----------------------------------------------------

    def record_images_updated(self, item_id, images_uploaded, operator_name,
                              status=work_log.STATUS_DONE, extra=None, logger=None):
        """
        يسجّل وحدة عمل واحدة (تحديث صور منتج) ثم يحاول دفعها.
        الترتيب مقصود: **التسجيل المحلي أولاً ودائماً**، حتى مع مزامنة مطفأة أو شبكة
        مقطوعة. الدفع الفاشل ليس فقداناً: المصالحة الكاملة التالية ستجد الوحدة بالسجل
        المحلي وترفعها. الدالة القديمة كانت تدفع مباشرة ولا تسجّل شيئاً محلياً، فأي
        فشل شبكة كان يعني عملاً ضائعاً من كل تقرير بلا أثر.
        يرجّع: {"recorded": bool, "pushed": bool, "error": str|None}
        """
        date_str, timestamp = work_log.now_parts()
        # الاسم القانوني من جدول أعضاء الخادم إن أمكن، وإلا الاسم المحلي كما هو.
        canonical_user = self.resolve_operator_identity(operator_name, logger=logger)
        unit = work_log.make_work_unit(
            user=canonical_user, date=date_str, item_id=item_id,
            status=status, quantity=images_uploaded, timestamp=timestamp,
            extra=extra,
        )
        recorded = work_log.append_unit(unit, logger=logger)
        result = {"recorded": recorded, "pushed": False, "error": None}

        if not self.configured:
            result["error"] = "sync_not_configured"
            if logger:
                logger.info(
                    "سُجّلت وحدة العمل محلياً لـ%s؛ المزامنة غير مُعدّة فلم تُرفع بعد "
                    "(ستُرفع تلقائياً بأول مصالحة بعد تفعيل المزامنة).", item_id,
                )
            return result

        pushed, error = self.push_unit(unit)
        result["pushed"] = pushed
        result["error"] = error
        if not pushed and logger:
            logger.warning(
                "الرفع نجح وسُجّل محلياً، لكن فشل دفعه لخادم المزامنة لـ%s: %s%s",
                item_id, error,
                " (تأكد إن SyncToken بالإعدادات يطابق $SECRET_TOKEN بملف sync.php بالضبط)"
                if error in ("Unauthorized", "sync_blocked_403") else "",
            )
        return result


def _sleep(seconds):
    """مُغلَّف منفصل ليسهل تعطيله بالاختبارات دون إبطائها."""
    import time
    time.sleep(seconds)
