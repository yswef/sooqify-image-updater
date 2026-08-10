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


def play_completion_sound():
    if os.name == "nt":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass


class Api:
    def __init__(self):
        self.logger = setup_logger(app_config.get_log_dir())
        self._window = None
        self.run_thread = None
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
        cfg = app_config.load_config()
        root = cfg.get("RootFolder", "")
        if not root or not os.path.isdir(root):
            return {"success": False, "error": "مجلد الحفظ غير صالح أو غير مُعد."}

        products = scanner.scan_root_folder(root)
        return {
            "success": True,
            "count": len(products),
            "products": [
                {
                    "folder_name": p.folder_name,
                    "path": p.path,
                    "style_code": p.style_code,
                    "name_en": p.name_en,
                    "name_ar": p.name_ar,
                    "images_count": len(p.images),
                    "has_search_key": p.has_search_key,
                    "info_found": p.info_found,
                }
                for p in products
            ],
        }

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

    def _run_pipeline(self, selected_paths, dry_run):
        cfg = app_config.load_config()
        root = cfg.get("RootFolder", "")
        all_products = {p.path: p for p in scanner.scan_root_folder(root)}
        targets = [all_products[p] for p in selected_paths if p in all_products]

        batch_limit = cfg.get("BatchLimit", 0)
        if batch_limit and batch_limit > 0:
            targets = targets[:batch_limit]

        self._push("run_started", {"total": len(targets), "dry_run": dry_run})

        sync = sync_client_module.SyncClient(cfg.get("SyncServerUrl", ""), cfg.get("SyncToken", ""))
        results = {"success": [], "skipped": [], "failed": []}

        if dry_run:
            for product in targets:
                if self.stop_requested:
                    break
                if not product.has_search_key:
                    results["skipped"].append({"folder": product.folder_name, "reason": "لا يوجد كود ستايل أو اسم للبحث."})
                else:
                    results["success"].append({"folder": product.folder_name, "reason": "جاهز (معاينة فقط - لم يُرفع شيء)."})
                self._push("product_done", {
                    "folder": product.folder_name, "status": "preview",
                    "index": len(results["success"]) + len(results["skipped"]) + len(results["failed"]),
                    "total": len(targets),
                })
            self._push("run_finished", results)
            return

        headless = bool(cfg.get("Headless", False))
        try:
            profile_dir = get_automation_profile_dir()
            if not os.listdir(profile_dir):
                raise RuntimeError(
                    "ما سجّلت دخولك لسوقيفاي بعد بمتصفح التطبيق. اضغط زر 'تسجيل الدخول' "
                    "بالشريط العلوي أول مرة، سجّل دخولك بالنافذة اللي تفتح، وأغلقها - وبعدها جرّب الرفع مرة ثانية."
                )
            launch_kwargs = get_browser_launch_kwargs("", cfg.get("Browser", "chrome"))

            self.logger.info(
                "جارِ فتح المتصفح (%s، headless=%s)...", cfg.get("Browser", "chrome"), headless
            )
            launch_started = time.monotonic()

            with sync_playwright() as playwright:
                context = _launch_browser(playwright, profile_dir, headless, launch_kwargs, logger=self.logger)

                self.logger.info("تم فتح المتصفح بنجاح خلال %.1f ثانية.", time.monotonic() - launch_started)

                # مهلة صريحة لكل تنقل/إجراء - أبداً ما نعتمد على الافتراضي الضمني،
                # عشان أي تعليق يطلع كخطأ واضح خلال ثوانٍ بدل ما يعلّق بصمت.
                context.set_default_timeout(NAVIGATION_TIMEOUT_MS)
                context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

                page = context.pages[0] if context.pages else context.new_page()

                for i, product in enumerate(targets, start=1):
                    if self.stop_requested:
                        self._push("run_stopped", {"completed": i - 1, "total": len(targets)})
                        break

                    self._push("product_started", {"folder": product.folder_name, "index": i, "total": len(targets)})
                    self.logger.info("[%s/%s] بدء معالجة: %s", i, len(targets), product.folder_name)
                    result = uploader.process_product_folder(
                        page, sync, product, cfg.get("OperatorName", ""), logger=self.logger
                    )
                    entry = {"folder": product.folder_name, "message": result.message}
                    if result.success:
                        results["success"].append(entry)
                    else:
                        results["failed"].append(entry)

                    self._push("product_done", {
                        "folder": product.folder_name,
                        "status": "success" if result.success else "failed",
                        "message": result.message,
                        "index": i, "total": len(targets),
                    })

                context.close()

        except Exception as exc:
            self.logger.error("توقف التشغيل بخطأ غير متوقع: %s", exc)
            self._push("run_error", {"error": str(exc)})
            return

        if cfg.get("SoundOnComplete", True):
            play_completion_sound()
        self._push("run_finished", results)


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