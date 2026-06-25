# =========================================================
# Sooqify Image Updater
# سجل طرفية ملوّن ومنظم، بنفس روح AlphaCode الأصلي.
# =========================================================
# تطوير: يوسف الحمزي

import logging
import os
import sys
from datetime import datetime


class AnsiColors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GRAY = "\033[90m"
    WHITE = "\033[97m"


def enable_windows_ansi_support():
    """تفعيل معالجة ألوان ANSI على cmd/PowerShell القديمة في ويندوز."""
    if os.name == "nt":
        os.system("")


enable_windows_ansi_support()


class ConsoleFormatter(logging.Formatter):
    """تنسيق ملوّن ومرتّب: وقت + رمز + مصدر + رسالة."""

    LEVEL_STYLE = {
        "DEBUG": (AnsiColors.GRAY, "·"),
        "INFO": (AnsiColors.CYAN, "*"),
        "WARNING": (AnsiColors.YELLOW, "!"),
        "ERROR": (AnsiColors.RED, "x"),
        "CRITICAL": (AnsiColors.RED + AnsiColors.BOLD, "X"),
    }

    def format(self, record):
        color, symbol = self.LEVEL_STYLE.get(record.levelname, (AnsiColors.WHITE, "*"))
        timestamp = self.formatTime(record, "%H:%M:%S")
        source_tag = record.name.upper()[:14].ljust(14)
        message = record.getMessage()
        return (
            f"{AnsiColors.GRAY}{timestamp}{AnsiColors.RESET} "
            f"{color}[{symbol}]{AnsiColors.RESET} "
            f"{AnsiColors.DIM}{source_tag}{AnsiColors.RESET} "
            f"{color}{message}{AnsiColors.RESET}"
        )


def setup_logger(log_dir, name="sooqify_updater"):
    """
    تهيئة سجل طرفية ملوّن + ملف سجل خارجي نصي عادي (بدون رموز ألوان).
    log_dir: مجلد حفظ ملف السجل (يُنشأ تلقائياً لو غير موجود).
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # تجنّب تكرار الإضافة لو استُدعيت أكثر من مرة.

    logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ConsoleFormatter())
    logger.addHandler(console_handler)

    try:
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "sooqify_updater.log")
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning("تعذّر إنشاء ملف السجل الخارجي: %s", exc)

    return logger


def print_startup_banner():
    """طباعة شعار ترحيبي عند تشغيل التطبيق."""
    os.system("cls" if os.name == "nt" else "clear")
    banner = r"""
========================================================================
========================================================================
**                                                                    **
**            SOOQIFY IMAGE UPDATER - محدّث صور سوقيفاي              **
**                                                                    **
**                     تطوير: يوسف الحمزي                            **
**                     Developed by Yousef Alhamzy                   **
**                                                                    **
========================================================================
========================================================================
"""
    print(f"{AnsiColors.GREEN}{AnsiColors.BOLD}{banner}{AnsiColors.RESET}")