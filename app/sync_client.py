# =========================================================
# Sooqify Image Updater
# Talks to sync.php itself (same AlphaCode system) - resolves product identity from the
# style code, and logs every successful image-upload run (shows up later in the
# AlphaCode report).
# =========================================================
# Developer: Yousef Alhamzy

from __future__ import annotations

import time
from typing import Any

import requests

REQUEST_TIMEOUT = (5, 10)  # (connect, read) seconds - short on purpose so the UI never hangs.

# Retry only genuinely transient failures (dropped connection, timeout, 5xx server
# errors) - never retry real client errors (401/403/404...), since those won't change
# by trying again.
MAX_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 1.0  # roughly 1s, then 2s, then 4s (exponential backoff).
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class SyncClient:
    def __init__(self, server_url: str, token: str) -> None:
        self.server_url = (server_url or "").rstrip("/")
        self.token = token or ""

    @property
    def configured(self) -> bool:
        return bool(self.server_url and self.token)

    def _call(
        self, action: str, payload: dict[str, Any] | None = None, method: str = "POST"
    ) -> tuple[dict[str, Any] | None, str | None]:
        if not self.configured:
            return None, "sync_not_configured"
        url = f"{self.server_url}/sync.php"
        headers = {"X-Sync-Token": self.token, "Content-Type": "application/json"}

        last_error: str | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if method == "GET":
                    response = requests.get(url, params={"action": action}, headers=headers, timeout=REQUEST_TIMEOUT)
                else:
                    response = requests.post(
                        url, params={"action": action}, headers=headers, json=payload or {}, timeout=REQUEST_TIMEOUT
                    )
            except requests.RequestException as exc:
                last_error = str(exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                    continue
                return None, last_error

            if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                last_error = f"HTTP {response.status_code}"
                time.sleep(RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                continue

            try:
                data = response.json()
            except ValueError as exc:
                return None, f"استجابة غير صالحة من خادم المزامنة: {exc}"

            if response.status_code >= 400:
                return data, data.get("error") or f"HTTP {response.status_code}"
            return data, None

        return None, last_error or "فشل الاتصال بعد عدة محاولات."

    def lookup_product_by_style_code(self, style_code: str) -> tuple[dict[str, Any] | None, str | None]:
        """
        Looks up a product by style code in the central sync system and returns its data
        (including the real id), instead of relying on any locally stored number.
        Returns: (product_dict or None, error message or None)
        """
        if not style_code:
            return None, "لا يوجد كود ستايل لهذا المنتج."
        data, error = self._call("lookup", {"key": style_code}, method="POST")
        if error:
            return None, error
        if data and data.get("success"):
            return data.get("product"), None
        return None, "لم يُعثر على المنتج بنظام المزامنة."

    def report_upload(self, product_key: str, images_uploaded: int, operator_name: str) -> None:
        """
        Logs a successful image-upload run - shows up later in the AlphaCode report as
        the "Updated Images" section. Never blocks on failure (best-effort logging - the
        actual upload already succeeded regardless).
        """
        if not self.configured:
            return
        self._call(
            "push",
            {
                "key": f"IMAGE_UPDATE_{product_key}",
                "product": {
                    "event": "image_update",
                    "product_key": product_key,
                    "images_uploaded": images_uploaded,
                    "updated_by": operator_name,
                },
            },
            method="POST",
        )
