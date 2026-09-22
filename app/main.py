# =========================================================
# Sooqify Image Updater
# نقطة تشغيل التطبيق - نافذة pywebview + ربط الواجهة بمنطق بايثون
# =========================================================

import os
import sys
import threading
import time

# عند التشغيل كملف exe مبني (PyInstaller)، متصفح Chromium يكون مرفق داخل
# مجلد "ms-browsers" جنب الـ exe (جهّزه خط البناء - راجع build/app.spec).
# لازم نوجّه Playwright له *قبل* استيراده، بدل ما يدوّر على تنزيل منفصل
# غير موجود على جهاز المستخدم. ما له أي أثر أبداً على التشغيل العادي
# (python main.py)، لأن sys.frozen غير موجودة إلا بالنسخة المبنية.
if getattr(sys, "frozen", False):
    _bundled_browsers = os.path.join(os.path.dirname(sys.executable), "ms-browsers")
    if os.path.isdir(_bundled_browsers):
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _bundled_browsers)

import webview
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as app_config
import scanner
import sync_client as sync_client_module
import uploader
import work_log
from logger_setup import setup_logger, print_startup_banner

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")

if os.name == "nt":
    COMMON_PROFILE_PATHS = {
        "chrome": r"%LOCALAPPDATA%\Google\Chrome\User Data",
        "brave": r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data",
        "edge": r"%LOCALAPPDATA%\Microsoft\Edge\User Data",
    }
elif sys.platform == "darwin":
    COMMON_PROFILE_PATHS = {
        "chrome": "~/Library/Application Support/Google/Chrome",
        "brave": "~/Library/Application Support/BraveSoftware/Brave-Browser",
        "edge": "~/Library/Application Support/Microsoft Edge",
    }
else:  # لينكس
    COMMON_PROFILE_PATHS = {
        "chrome": "~/.config/google-chrome",
        "brave": "~/.config/BraveSoftware/Brave-Browser",
        "edge": "~/.config/microsoft-edge",
    }


# مهلات صريحة (مليثانية) - أي عملية متصفح لازم تنتهي أو تفشل بوضوح خلال هالوقت،
# ما نعتمد أبداً على القيم الافتراضية الضمنية اللي قد تختلف حسب النظام.
NAVIGATION_TIMEOUT_MS = 20000
BROWSER_LAUNCH_TIMEOUT_MS = 45000
BROWSER_LAUNCH_RETRY_TIMEOUT_MS = 90000  # محاولة ثانية أطول - أول فتح لبروفايل جديد كلياً قد يكون أبطأ من المعتاد.


def _launch_browser(playwright, profile_dir, headless, launch_kwargs, logger=None):
    """يحاول فتح المتصفح، وبمحاولة ثانية بمهلة أطول لو فشلت الأولى بتايم آوت (شائع بأول فتح لبروفايل جديد)."""
    last_exc = None
    for attempt, timeout_ms in enumerate([BROWSER_LAUNCH_TIMEOUT_MS, BROWSER_LAUNCH_RETRY_TIMEOUT_MS], start=1):
        try:
            return playwright.chromium.launch_persistent_context(
                profile_dir, headless=headless, no_viewport=True,
                timeout=timeout_ms, **launch_kwargs,
            )
        except Exception as exc:
            last_exc = exc
            if logger:
                logger.warning(
                    "محاولة %s: فشل فتح المتصفح خلال %.0f ثانية (%s). %s",
                    attempt, timeout_ms / 1000, exc,
                    "جارِ محاولة أخرى بمهلة أطول..." if attempt == 1 else "",
                )
    raise RuntimeError(
        f"فشل فتح المتصفح بمحاولتين (حتى {BROWSER_LAUNCH_RETRY_TIMEOUT_MS/1000:.0f} ثانية بالمحاولة الأخيرة). "
        f"تأكد إن المتصفح مثبّت فعلياً، ولو السيرفر بدون شاشة فعّل 'Headless' بالإعدادات. تفاصيل الخطأ: {last_exc}"
    ) from last_exc


def get_automation_profile_dir():
    """
    مجلد بروفايل مخصص لهذا التطبيق فقط (منفصل تماماً عن بروفايل كروم الشخصي).
    يُنشأ فاضياً أول مرة، تسجّل دخولك فيه مرة وحدة عبر login_browser()، وبعدها
    كروميوم نفسه يحفظ الكوكيز/الجلسة بداخله تلقائياً - بدون أي نسخ لاحقاً، وبدون
    تحميل إضافاتك الشخصية أو بيانات متصفحك الحقيقي (وهذا سبب البطء الأساسي سابقاً).
    """
    path = os.path.join(app_config.get_config_dir(), "browser_profile")
    os.makedirs(path, exist_ok=True)
    return path


def expand_profile_path(raw_path):
    """يوسّع %VAR% (ويندوز) و ~ (لينكس/ماك) بنفس الدالة، بغض النظر عن المنصة."""
    return os.path.expanduser(os.path.expandvars(raw_path or ""))


def get_browser_launch_kwargs(user_data_dir_lower, browser_choice):
    kwargs = {}
    if browser_choice == "brave":
        if os.name == "nt":
            brave_paths = [
                os.path.expandvars(r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            ]
        elif sys.platform == "darwin":
            brave_paths = ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
        else:
            brave_paths = ["/usr/bin/brave-browser", "/usr/bin/brave", "/snap/bin/brave"]
        for p in brave_paths:
            if os.path.exists(p):
                kwargs["executable_path"] = p
                break
    elif browser_choice == "chrome":
        kwargs["channel"] = "chrome"
    elif browser_choice == "edge":
        kwargs["channel"] = "msedge"
    return kwargs


def _is_inside(candidate_path, parent_path):
    """هل candidate_path يقع فعلاً داخل parent_path؟ (يمنع الخروج بـ".." أو مسار مطلق آخر)."""
    if not candidate_path or not parent_path:
        return False
    try:
        candidate = os.path.abspath(candidate_path)
        parent = os.path.abspath(parent_path)
        return os.path.commonpath([candidate, parent]) == parent
    except ValueError:
        # مسارات على أقراص مختلفة بويندوز - commonpath يرمي ValueError.
        return False


def _unique_destination(dest_path):
    """
    يرجّع مساراً غير موجود: dest، ثم dest_2، dest_3... **لا يحذف شيئاً أبداً.**
    الحد الأعلى يمنع حلقة لا نهائية لو تعذّر إنشاء اسم فريد لأي سبب.
    """
    if not os.path.exists(dest_path):
        return dest_path
    for suffix in range(2, 1000):
        candidate = f"{dest_path}_{suffix}"
        if not os.path.exists(candidate):
            return candidate
    raise RuntimeError(f"تعذّر إيجاد اسم أرشيف غير مستخدم لـ{dest_path}")


class Api:
    def __init__(self):
        self.logger = setup_logger(app_config.get_log_dir())
        self._window = None
        self.run_thread = None
        self.scan_thread = None
        self.stop_requested = False

    def bind_window(self, window):
        self._window = window

    def _push(self, event, payload=None):
        if not self._window:
            return
        try:
            import json
            # استخدام evaluate_js عبر النافذة بشكل آمن
            self._window.evaluate_js(f"window.onBackendEvent({json.dumps({'event': event, 'payload': payload})})")
        except Exception:
            pass

    def get_config(self):
        return app_config.load_config()

    def save_config(self, values):
        return app_config.save_config(values)

    def choose_root_folder(self):
        if not self._window:
            return ""
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else ""

    def suggest_browser_profile_path(self, browser):
        return expand_profile_path(COMMON_PROFILE_PATHS.get(browser, ""))

    def login_browser(self):
        if self.run_thread and self.run_thread.is_alive():
            return {"success": False, "error": "يوجد تشغيل جارٍ بالفعل - أوقفه أولاً."}
        self.stop_requested = False
        self.run_thread = threading.Thread(target=self._login_flow, daemon=True)
        self.run_thread.start()
        return {"success": True}

    def _login_flow(self):
        cfg = app_config.load_config()
        profile_dir = get_automation_profile_dir()
        launch_kwargs = get_browser_launch_kwargs("", cfg.get("Browser", "chrome"))
        self.logger.info("جارِ فتح متصفح مخصص لتسجيل الدخول (منفصل عن متصفحك الشخصي)...")
        try:
            with sync_playwright() as playwright:
                try:
                    context = _launch_browser(playwright, profile_dir, False, launch_kwargs, logger=self.logger)
                except Exception as exc:
                    raise RuntimeError(f"فشل فتح المتصفح: {exc}") from exc

                page = context.pages[0] if context.pages else context.new_page()
                try:
                    page.goto(uploader.LIST_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
                except Exception:
                    pass  # لو ما فتحت الصفحة لأي سبب (قبل تسجيل الدخول)، خلي المستخدم يكمل يدوياً

                self._push("login_ready", {})
                self.logger.info("سجّل دخولك بلوحة سوقيفاي بالنافذة اللي فتحت، وبعدها أغلقها عادي - بيانات الدخول تُحفظ تلقائياً بدون أي خطوة إضافية.")
                try:
                    page.wait_for_event("close", timeout=0)
                except Exception:
                    pass
                try:
                    context.close()
                except Exception:
                    pass
            self.logger.info("تم حفظ جلسة الدخول بنجاح.")
            self._push("login_finished", {"success": True})
        except Exception as exc:
            self.logger.error("فشل تسجيل الدخول: %s", exc)
            self._push("login_finished", {"success": False, "error": str(exc)})

    def scan_products(self):
        if self.scan_thread and self.scan_thread.is_alive():
            return {"success": False, "error": "هناك عملية فحص جارية بالفعل."}

        cfg = app_config.load_config()
        root = cfg.get("RootFolder", "")
        if not root or not os.path.isdir(root):
            return {"success": False, "error": "مجلد الحفظ غير صالح أو غير مُعد."}

        self.scan_thread = threading.Thread(
            target=self._async_scan_flow, args=(root,), daemon=True
        )
        self.scan_thread.start()
        return {"success": True}

    def _async_scan_flow(self, root):
        try:
            self._push("scan_started", {})
            def scan_cb(folder_name, current_count):
                self._push("scan_progress", {"folder": folder_name, "count": current_count})

            products = scanner.scan_root_folder(root, progress_callback=scan_cb)
            payload = [
                {
                    "folder_name": p.folder_name,
                    "path": p.path,
                    "style_code": p.style_code,
                    "product_id": p.product_id,
                    "name_en": p.name_en,
                    "name_ar": p.name_ar,
                    "images_count": len(p.images),
                    "has_search_key": p.has_search_key,
                    "info_found": p.info_found,
                }
                for p in products
            ]
            self._push("scan_finished", {"success": True, "products": payload, "count": len(payload)})
        except Exception as exc:
            self.logger.error("فشل فحص الملفات: %s", exc)
            self._push("scan_finished", {"success": False, "error": str(exc)})

    def start_run(self, selected_paths, dry_run=True):
        if self.run_thread and self.run_thread.is_alive():
            return {"success": False, "error": "يوجد تشغيل جارٍ بالفعل."}

        self.stop_requested = False
        self.run_thread = threading.Thread(
            target=self._run_pipeline, args=(selected_paths, dry_run), daemon=True
        )
        self.run_thread.start()
        return {"success": True}

    def stop_run(self):
        self.stop_requested = True
        return {"success": True}

    def reconcile_sync(self):
        """
        مصالحة كاملة فورية بطلب المشغّل (نظير /api/sync/reconcile بـAlphaCode).
        ترجّع أرقاماً صريحة: العدد المحلي، العدد على الخادم، والفارق بينهما.
        """
        cfg = app_config.load_config()
        sync = sync_client_module.SyncClient(cfg.get("SyncServerUrl", ""), cfg.get("SyncToken", ""))
        if not sync.configured:
            return {"success": False, "error": "المزامنة غير مُعدّة (رابط الخادم أو كود المزامنة فاضٍ)."}
        try:
            return sync.reconcile_work_units(logger=self.logger)
        except Exception as exc:
            self.logger.error("فشلت المصالحة اليدوية: %s", exc)
            return {"success": False, "error": str(exc)}

    def get_sync_status(self):
        """حالة المزامنة المحلية: آخر مصالحة، آخر خطأ، وآخر فارق عدد معلَن."""
        state = work_log.load_sync_state()
        units, corrupt = work_log.load_units()
        return {
            "success": True,
            "local_units": len(work_log.units_by_key(units)),
            "corrupt_local_lines": corrupt,
            "last_reconcile_at": state.get("last_reconcile_at") or "",
            "last_error": state.get("last_error") or "",
            "last_delta": state.get("last_delta"),
            "last_in_sync": state.get("last_in_sync"),
        }

    def _run_pipeline(self, selected_paths, dry_run):
        cfg = app_config.load_config()
        root = cfg.get("RootFolder", "")
        # نفحص المجلدات المحددة فقط. سابقاً كانت الشجرة كاملة تُمسح من جديد هنا
        # (بعد أن مسحها خيط الفحص للتو)، وبآلاف المجلدات كان ذلك تأخيراً محسوساً
        # قبل أن يفتح المتصفح أصلاً.
        targets = []
        for selected in selected_paths or []:
            # حارس: لا نعالج أي مسار خارج المجلد الرئيسي، حتى لو تغيّر RootFolder
            # بالإعدادات بين الفحص والتشغيل.
            if not _is_inside(selected, root):
                self.logger.warning("تم تجاهل مسار خارج المجلد الرئيسي: %s", selected)
                continue
            product = scanner.scan_product_folder(selected)
            if product:
                targets.append(product)
            else:
                self.logger.warning("تم تجاهل مجلد لم يعد يحتوي صوراً: %s", selected)

        batch_limit = cfg.get("BatchLimit", 0)
        if batch_limit and batch_limit > 0:
            targets = targets[:batch_limit]

        self._push("run_started", {"total": len(targets), "dry_run": dry_run})

        sync = sync_client_module.SyncClient(cfg.get("SyncServerUrl", ""), cfg.get("SyncToken", ""))
        results = {"success": [], "skipped": [], "failed": []}

        # ─── تحديد وضع المتصفح ───
        # وضع المراجعة (dry_run): متصفح مرئي - المستخدم يراجع ويعتمد يدوياً
        # الوضع التلقائي (بدون dry_run): متصفح خفي (headless) - تلقائي بالكامل
        if dry_run:
            headless = False
        else:
            headless = True

        total_images = 0
        try:
            profile_dir = get_automation_profile_dir()
            if not os.listdir(profile_dir):
                raise RuntimeError(
                    "ما سجّلت دخولك لسوقيفاي بعد بمتصفح التطبيق. اضغط زر 'تسجيل الدخول' "
                    "بالشريط العلوي أول مرة، سجّل دخولك بالنافذة اللي تفتح، وأغلقها - وبعدها جرّب الرفع مرة ثانية."
                )
            launch_kwargs = get_browser_launch_kwargs("", cfg.get("Browser", "chrome"))

            mode_label = "وضع المراجعة (متصفح مرئي)" if dry_run else "وضع تلقائي (بالخلفية)"
            self.logger.info(
                "جارِ فتح المتصفح — %s (%s، headless=%s)...", mode_label, cfg.get("Browser", "chrome"), headless
            )
            launch_started = time.monotonic()

            with sync_playwright() as playwright:
                context = _launch_browser(playwright, profile_dir, headless, launch_kwargs, logger=self.logger)

                self.logger.info("تم فتح المتصفح بنجاح خلال %.1f ثانية.", time.monotonic() - launch_started)

                # مهلة صريحة لكل تنقل/إجراء
                context.set_default_timeout(NAVIGATION_TIMEOUT_MS)
                context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

                page = context.pages[0] if context.pages else context.new_page()

                # تحقق فعلي من الجلسة قبل لمس أي منتج - بدل فشل كل المنتجات واحداً
                # واحداً ونقلها لمجلدات فشل بسبب جلسة منتهية.
                session_ok, session_error = uploader.verify_store_session(page, logger=self.logger)
                if not session_ok:
                    self.logger.error("%s", session_error)
                    self._push("run_error", {"error": session_error})
                    try:
                        context.close()
                    except Exception:
                        pass
                    return

                for i, product in enumerate(targets, start=1):
                    if self.stop_requested:
                        self._push("run_stopped", {"completed": i - 1, "total": len(targets)})
                        break

                    if not product.has_search_key:
                        results["skipped"].append({"folder": product.folder_name, "reason": "لا يوجد كود ستايل أو اسم للبحث."})
                        self._push("product_done", {
                            "folder": product.folder_name, "status": "skipped",
                            "message": "لا يوجد مفتاح بحث — تم تخطّيه.",
                            "index": i, "total": len(targets),
                        })
                        continue

                    self._push("product_started", {"folder": product.folder_name, "index": i, "total": len(targets)})
                    self.logger.info("[%s/%s] بدء معالجة: %s", i, len(targets), product.folder_name)
                    result = uploader.process_product_folder(
                        page, sync, product, cfg.get("OperatorName", ""),
                        dry_run=dry_run, logger=self.logger
                    )
                    entry = {"folder": product.folder_name, "message": result.message}
                    if result.success:
                        results["success"].append(entry)
                        total_images += result.images_uploaded
                    else:
                        results["failed"].append(entry)

                    status = "success" if result.success else "failed"
                    if dry_run and result.success:
                        status = "review"

                    self._push("product_done", {
                        "folder": product.folder_name,
                        "status": status,
                        "message": result.message,
                        "index": i, "total": len(targets),
                    })

                    # في وضع المراجعة: ننتظر المستخدم يعتمد يدوياً (الصفحة تروح للقائمة بعد الاعتماد)
                    if dry_run and result.success:
                        self.logger.info("⏳ بانتظار اعتمادك اليدوي من المتصفح لـ '%s'...", product.folder_name)
                        self._push("waiting_approval", {"folder": product.folder_name, "index": i, "total": len(targets)})
                        try:
                            page.wait_for_url(f"**{uploader.LIST_PAGE_URL_FRAGMENT}**", timeout=300000)  # 5 دقائق حد أقصى
                            self.logger.info("✓ تم اعتماد '%s' بنجاح.", product.folder_name)
                        except Exception:
                            self.logger.warning("⏰ انتهت مهلة الانتظار لاعتماد '%s' — الانتقال للمنتج التالي.", product.folder_name)

                    # نقل المجلد تلقائياً بعد الفراغ منه (فقط الوضع التلقائي)
                    if not dry_run and cfg.get("MoveFoldersAfterUpload", True):
                        self._relocate_product(product.path, root, result.success, result.message)

                    # تنظيف تبويبات إضافية قد يفتحها الموقع بعد الحفظ
                    if len(context.pages) > 1:
                        for p in context.pages[1:]:
                            try:
                                p.close()
                            except Exception:
                                pass
                                
                context.close()

        except Exception as exc:
            self.logger.error("توقف التشغيل بخطأ غير متوقع: %s", exc)
            self._push("run_error", {"error": str(exc)})
            return

        # مصالحة كاملة لوحدات العمل بنهاية الدفعة (شفاء ذاتي) — فقط الوضع التلقائي.
        # تُستدعى تلقائياً، لأن فجوة AlphaCode بقيت شهراً بسبب مصالحة موجودة لا يستدعيها شيء.
        # فارق العدد بين المحلي والبعيد يُعلَن للمشغّل صراحةً بدل ابتلاعه بصمت.
        if not dry_run and sync.configured:
            try:
                reconcile = sync.auto_reconcile_if_due(logger=self.logger)
            except Exception as exc:
                # فشل المصالحة لا يُبطل نجاح الدفعة نفسها، لكنه يُعلَن ولا يُبتلع.
                self.logger.warning("تعذّرت مصالحة وحدات العمل بنهاية الدفعة: %s", exc)
                reconcile = {"success": False, "error": str(exc)}
            if reconcile:
                results["sync"] = reconcile
                self._push("sync_reconciled", reconcile)

        # ملاحظة: نغمة الاكتمال تُشغَّل من الواجهة (playCompletionBeep بـapp.js) عند
        # استقبال run_finished. كانت تُشغَّل من الطرفين معاً على نفس الحدث فتُسمع
        # نغمتان. أُبقيت نغمة الواجهة لأنها تعمل على كل المنصات، بينما winsound
        # كان يعمل على ويندوز وحده.
        self._push("run_finished", results)

    def _relocate_product(self, product_path, root_folder, success, error_message=None):
        """
        ينقل مجلد المنتج بعد الفراغ منه إلى شجرة الأرشيف، **بلا حذف أي شيء أبداً**
        وبالحفاظ على مساره النسبي تحت المجلد الرئيسي.

        العيب المُصلَح: كانت الأرشفة مسطّحة باسم المجلد الأخير فقط، ولو وُجد بالوجهة
        مجلد بنفس الاسم كان يُحذف بـshutil.rmtree ثم يُكتب فوقه. مع تنظيم
        براند/تاريخ/منتج يصير التصادم شبه مؤكد: BrandA/A1 و BrandB/A1 ينتهيان لنفس
        الوجهة، فتُمحى صور BrandA نهائياً بلا سؤال ولا تحذير، والسجل يقول "تم النقل
        بنجاح". أُثبت هذا عملياً.

        الآن: الوجهة تعكس شجرة المصدر (images_uploaded/BrandA/2026-09-01/A1) فلا
        تصادم أصلاً؛ وإن حصل تصادم رغم ذلك تُضاف لاحقة رقمية بدل الحذف.
        """
        import shutil

        folder_name = os.path.basename(os.path.abspath(product_path))
        try:
            if not _is_inside(product_path, root_folder):
                # حارس: لا ننقل شيئاً خارج المجلد الرئيسي مهما كان.
                self.logger.error(
                    "أُلغي نقل '%s': المسار خارج المجلد الرئيسي (%s).", product_path, root_folder
                )
                return False

            root_abs = os.path.abspath(root_folder)
            parent_dir = os.path.dirname(root_abs)
            relative_path = os.path.relpath(os.path.abspath(product_path), root_abs)

            if success:
                archive_root = os.path.join(parent_dir, f"{os.path.basename(root_abs)}_uploaded")
                dest_path = os.path.join(archive_root, relative_path)
                label = "الأرشفة"
            else:
                category = self._classify_failure(error_message)
                archive_root = os.path.join(parent_dir, f"{os.path.basename(root_abs)}_failed", category)
                dest_path = os.path.join(archive_root, relative_path)
                label = f"الفشل ({category})"

            dest_path = _unique_destination(dest_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.move(product_path, dest_path)
            self.logger.info("تم نقل المجلد لـ%s: %s -> %s", label, folder_name, dest_path)
            return True
        except Exception as exc:
            self.logger.error(
                "فشل نقل وأرشفة المجلد %s لـ%s: %s",
                folder_name, "نجاح" if success else "فشل", exc,
            )
            return False

    @staticmethod
    def _classify_failure(error_message):
        """يصنّف سبب الفشل لمجلد فرعي مفهوم، بدل رمي كل الفشل بسلة واحدة."""
        msg = error_message or ""
        if "بلا كود ستايل أو اسم" in msg:
            return "حذف_مفتاح_البحث"
        if "غير موجود بالمتجر" in msg:
            return "غير_موجود_في_المتجر"
        if "مطابق للعلامات" in msg or "فشل التحقق" in msg:
            return "عدم_تطابق_الهوية"
        if "رفع ناقص" in msg:
            # تصنيف جديد: رُفع بعض الصور فقط ولم يُضغط "اعتماد" - يحتاج مراجعة يدوية،
            # وصور المنتج بالمتجر ما زالت القديمة سليمة.
            return "رفع_ناقص"
        if "صور سابقة تمنع الرفع" in msg or "حذف الصور القديمة يدوياً" in msg:
            return "صور_قديمة_تمنع_الرفع"
        if "network/timeout" in msg or "الشبكة" in msg or "فشلت عملية الرفع" in msg:
            return "خطأ_اتصال_بالشبكة"
        if "الحفظ لم يُؤكَّد" in msg:
            return "فشل_حفظ_التعديلات"
        return "أخطاء_أخرى"


def main():
    print_startup_banner()
    api = Api()
    window = webview.create_window(
        "Sooqify Image Updater — تطوير: يوسف الحمزي",
        os.path.join(UI_DIR, "index.html"),
        js_api=api,
        width=1180,
        height=820,
        min_size=(980, 680),
    )
    api.bind_window(window)
    if os.name == "nt":
        # استخدام محرك edgechromium لحل مشكلة WinForms / Accessibility (ويندوز فقط)
        webview.start(gui='edgechromium')
    else:
        # على لينكس/ماك نترك pywebview يختار المحرك المتاح تلقائياً (gtk/qt/cocoa)
        webview.start()


if __name__ == "__main__":
    main()