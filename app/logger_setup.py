# =========================================================
# Sooqify Image Updater
# A colorized, structured console logger, in the same spirit as the original AlphaCode.
# =========================================================
# Developer: Yousef Alhamzy

from __future__ import annotations

import logging
import os
import sys


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


def enable_windows_ansi_support() -> None:
    """Enable ANSI color handling on older Windows cmd/PowerShell."""
    if os.name == "nt":
        os.system("")


enable_windows_ansi_support()


class ConsoleFormatter(logging.Formatter):
    """A tidy, colorized format: time + icon + source + message."""

    LEVEL_STYLE = {
        "DEBUG": (AnsiColors.GRAY, "·"),
        "INFO": (AnsiColors.CYAN, "*"),
        "WARNING": (AnsiColors.YELLOW, "!"),
        "ERROR": (AnsiColors.RED, "x"),
        "CRITICAL": (AnsiColors.RED + AnsiColors.BOLD, "X"),
    }

    def format(self, record: logging.LogRecord) -> str:
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


def setup_logger(log_dir: str, name: str = "sooqify_updater") -> logging.Logger:
    """
    Sets up a colorized console logger + a plain-text log file (no color codes).
    log_dir: folder to store the log file in (created automatically if missing).
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # Avoid adding duplicate handlers if this is called more than once.

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


def print_startup_banner() -> None:
    """Prints a startup banner when the app launches."""
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