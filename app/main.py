# =========================================================
# Sooqify Image Updater
# App entry point - pywebview window + wiring the frontend to the Python backend.
# =========================================================

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any

import webview
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as app_config
import scanner
import sync_client as sync_client_module
import uploader
from logger_setup import setup_logger, print_startup_banner

# In a normal source checkout, the project root is the parent of app/. In a PyInstaller
# --onefile build, everything bundled via `datas` is extracted under sys._MEIPASS at
# runtime instead - both cases resolve to the same "app/ui" layout underneath.
if getattr(sys, "frozen", False):
    _PROJECT_ROOT = sys._MEIPASS
else:
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_DIR = os.path.join(_PROJECT_ROOT, "app", "ui")

# Explicit timeouts (milliseconds) - any browser operation must either finish or fail
# clearly within this window. We never rely on implicit defaults, which can vary by
# machine and used to cause silent multi-minute hangs.
NAVIGATION_TIMEOUT_MS = 20000
BROWSER_LAUNCH_TIMEOUT_MS = 45000

# Lock files Chrome/Chromium-based browsers write at the root of a user-data-dir to
# claim exclusive ownership of that profile. If a previous run crashed, was force-quit,
# or is still lingering, these files (and the process holding them) block any new
# launch pointed at the same profile - Playwright then just sits there until its own
# timeout fires, with no useful error. We clear both before every launch.
_SINGLETON_LOCK_FILES = ("SingletonLock", "SingletonCookie", "SingletonSocket")


def _clear_stale_profile_lock(profile_dir: str) -> None:
    """Remove leftover singleton lock files from a previous crashed/killed run."""
    for name in _SINGLETON_LOCK_FILES:
        path = os.path.join(profile_dir, name)
        try:
            if os.path.exists(path) or os.path.islink(path):
                os.remove(path)
        except OSError:
            pass  # Best effort - a launch failure below will still surface clearly.


def _kill_stale_profile_processes(profile_dir: str, logger: Any = None) -> None:
    """
    Terminate any leftover browser process that was launched against OUR OWN dedicated
    profile directory specifically (never a broad "kill every chrome.exe" - that would
    also close the operator's personal, unrelated browser windows). Matches on the
    profile path appearing in the process command line, so only our own app-owned
    profile is ever touched.
    """
    try:
        import psutil
    except ImportError:
        return  # Optional dependency - if unavailable we just skip this precise cleanup.

    normalized_profile_dir = os.path.normcase(os.path.normpath(profile_dir))
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if not cmdline:
                continue
            joined = os.path.normcase(" ".join(cmdline))
            if normalized_profile_dir in joined:
                if logger:
                    logger.warning(
                        "Killing a leftover browser process still holding our profile (pid=%s)...", proc.pid
                    )
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # Give the OS a brief moment to actually release the file handles/lock.
    time.sleep(0.5)


def prepare_profile_for_launch(profile_dir: str, logger: Any = None) -> None:
    """Clear anything that could make launch_persistent_context hang on a stale lock."""
    _kill_stale_profile_processes(profile_dir, logger=logger)
    _clear_stale_profile_lock(profile_dir)


# ---------------------------------------------------------------------------
# Browser profile: owned by the app only - never a copy of the operator's real profile.
#
# The previous design copied the operator's entire real Chrome profile (browsing
# history, cookies, every installed extension, account sync data, etc.) into a temp
# folder on every live run (~227MB in one observed case, ~70+ seconds by itself), then
# launched Chrome with all of those personal extensions active - which is what caused
# the long silent hang at "opening browser...".
#
# The replacement: a lightweight, app-owned profile (app_config.get_browser_profile_dir)
# - completely empty the first time, with no extensions or personal data. You log into
# Sooqify inside it exactly once (the "Log in to Sooqify" action in Settings), and the
# persistent context remembers that login automatically afterward - no copying, and no
# personal browser data ever loaded.
# ---------------------------------------------------------------------------


def get_browser_launch_kwargs(browser_choice: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
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


def play_completion_sound() -> None:
    if os.name == "nt":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass


def _launch_error_message(exc: Exception, browser_choice: str) -> str:
    return (
        f"فشل فتح المتصفح خلال {BROWSER_LAUNCH_TIMEOUT_MS/1000:.0f} ثانية. غالباً السبب واحد من التالي:\n"
        f"  • عملية {browser_choice} سابقة عالقة كانت لسه ماسكة نفس بروفايل التطبيق (نظّفنا القفل تلقائياً "
        f"قبل هالمحاولة - جرّب مرة ثانية، لو استمرت أعد تشغيل الجهاز).\n"
        f"  • برنامج حماية/جدار حماية (مثل مضاد فيروسات أو أداة مراقبة شبكة) يمنع الاتصال المحلي بين "
        f"التطبيق والمتصفح - أضف استثناء له.\n"
        f"  • المتصفح ({browser_choice}) غير مثبّت فعلياً على هذا الجهاز.\n"
        f"  • لو السيرفر بدون شاشة عرض، فعّل 'Headless' بالإعدادات.\n"
        f"تفاصيل الخطأ التقنية: {exc}"
    )


class Api:
    def __init__(self) -> None:
        self.logger = setup_logger(app_config.get_log_dir())
        self._window: webview.Window | None = None
        self.run_thread: threading.Thread | None = None
        self.login_thread: threading.Thread | None = None
        self.stop_requested = False

    def bind_window(self, window: webview.Window) -> None:
        self._window = window

    def _push(self, event: str, payload: Any = None) -> None:
        if not self._window:
            return
        try:
            self._window.evaluate_js(f"window.onBackendEvent({json.dumps({'event': event, 'payload': payload})})")
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Settings
    # -----------------------------------------------------------------

    def get_config(self) -> dict[str, Any]:
        """Config for the UI - deliberately without the secret token (kept in the OS credential store only)."""
        config = app_config.load_config()
        config["HasSyncToken"] = bool(app_config.load_sync_token())
        return config

    def save_config(self, values: dict[str, Any]) -> dict[str, Any]:
        saved = app_config.save_config(values)
        saved["HasSyncToken"] = bool(app_config.load_sync_token())
        return saved

    def choose_root_folder(self) -> str:
        if not self._window:
            return ""
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else ""

    # -----------------------------------------------------------------
    # Sooqify login - once, always in a visible browser regardless of the Headless setting.
    # -----------------------------------------------------------------

    def start_login(self) -> dict[str, Any]:
        if self.login_thread and self.login_thread.is_alive():
            return {"success": False, "error": "نافذة تسجيل الدخول مفتوحة بالفعل."}
        if self.run_thread and self.run_thread.is_alive():
            return {"success": False, "error": "يوجد تشغيل جارٍ بالفعل - أوقفه أولاً."}

        cfg = app_config.load_config()
        self.login_thread = threading.Thread(
            target=self._run_login, args=(cfg.get("Browser", "chrome"),), daemon=True
        )
        self.login_thread.start()
        return {"success": True}

    def _run_login(self, browser_choice: str) -> None:
        profile_dir = app_config.get_browser_profile_dir()
        launch_kwargs = get_browser_launch_kwargs(browser_choice)
        self.logger.info("Opening browser for login (app-owned dedicated profile)...")
        self._push("login_started")
        prepare_profile_for_launch(profile_dir, logger=self.logger)
        try:
            with sync_playwright() as playwright:
                try:
                    context = playwright.chromium.launch_persistent_context(
                        profile_dir,
                        headless=False,  # Login must always be visible, regardless of the Headless setting.
                        no_viewport=True,
                        timeout=BROWSER_LAUNCH_TIMEOUT_MS,
                        ignore_default_args=["--disable-extensions", "--enable-automation"],
                        **launch_kwargs,
                    )
                except Exception as exc:
                    raise RuntimeError(_launch_error_message(exc, browser_choice)) from exc
                context.set_default_timeout(NAVIGATION_TIMEOUT_MS)
                context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(uploader.LIST_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
                self.logger.info("Log in inside the opened browser, then close it when done - it saves automatically.")
                # Wait for the operator to close the browser manually (no timeout) - by then the
                # session is already saved into the profile directory.
                page.wait_for_event("close", timeout=0)
        except Exception as exc:
            self.logger.error("Could not open the login browser: %s", exc)
            self._push("login_error", {"error": str(exc)})
            return
        self.logger.info("Login session ended.")
        self._push("login_finished")

    # -----------------------------------------------------------------
    # Scan and run
    # -----------------------------------------------------------------

    def scan_products(self) -> dict[str, Any]:
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

    def start_run(self, selected_paths: list[str], dry_run: bool = True) -> dict[str, Any]:
        if self.run_thread and self.run_thread.is_alive():
            return {"success": False, "error": "يوجد تشغيل جارٍ بالفعل."}
        if self.login_thread and self.login_thread.is_alive():
            return {"success": False, "error": "أغلق نافذة تسجيل الدخول أولاً."}

        self.stop_requested = False
        self.run_thread = threading.Thread(
            target=self._run_pipeline, args=(selected_paths, dry_run), daemon=True
        )
        self.run_thread.start()
        return {"success": True}

    def stop_run(self) -> dict[str, Any]:
        self.stop_requested = True
        return {"success": True}

    def _run_pipeline(self, selected_paths: list[str], dry_run: bool) -> None:
        cfg = app_config.load_config_with_token()
        root = cfg.get("RootFolder", "")
        all_products = {p.path: p for p in scanner.scan_root_folder(root)}
        targets = [all_products[p] for p in selected_paths if p in all_products]

        batch_limit = cfg.get("BatchLimit", 0)
        if batch_limit and batch_limit > 0:
            targets = targets[:batch_limit]

        self._push("run_started", {"total": len(targets), "dry_run": dry_run})

        sync = sync_client_module.SyncClient(cfg.get("SyncServerUrl", ""), cfg.get("SyncToken", ""))
        results: dict[str, list[dict[str, Any]]] = {"success": [], "skipped": [], "failed": []}

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
        browser_choice = cfg.get("Browser", "chrome")
        profile_dir = app_config.get_browser_profile_dir()
        try:
            launch_kwargs = get_browser_launch_kwargs(browser_choice)

            self.logger.info("Opening browser (%s, headless=%s)...", browser_choice, headless)
            prepare_profile_for_launch(profile_dir, logger=self.logger)
            launch_started = time.monotonic()

            with sync_playwright() as playwright:
                try:
                    context = playwright.chromium.launch_persistent_context(
                        profile_dir,
                        headless=headless,
                        no_viewport=True,
                        timeout=BROWSER_LAUNCH_TIMEOUT_MS,
                        ignore_default_args=["--disable-extensions", "--enable-automation"],
                        **launch_kwargs,
                    )
                except Exception as exc:
                    raise RuntimeError(_launch_error_message(exc, browser_choice)) from exc

                self.logger.info("Browser opened successfully in %.1fs.", time.monotonic() - launch_started)

                # Explicit timeout for every navigation/action - never rely on the implicit
                # default, so any hang surfaces as a clear error within seconds instead of
                # hanging silently.
                context.set_default_timeout(NAVIGATION_TIMEOUT_MS)
                context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

                page = context.pages[0] if context.pages else context.new_page()

                for i, product in enumerate(targets, start=1):
                    if self.stop_requested:
                        self._push("run_stopped", {"completed": i - 1, "total": len(targets)})
                        break

                    self._push("product_started", {"folder": product.folder_name, "index": i, "total": len(targets)})
                    self.logger.info("[%s/%s] Processing: %s", i, len(targets), product.folder_name)
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
            self.logger.error("Run stopped due to an unexpected error: %s", exc)
            self._push("run_error", {"error": str(exc)})
            return

        if cfg.get("SoundOnComplete", True):
            play_completion_sound()
        self._push("run_finished", results)


def main() -> None:
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
        # Use the edgechromium engine to work around WinForms/Accessibility issues (Windows only).
        webview.start(gui='edgechromium')
    else:
        # On Linux/macOS, let pywebview auto-pick whichever engine is available (gtk/qt/cocoa).
        webview.start()


if __name__ == "__main__":
    main()
