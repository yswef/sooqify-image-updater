# =========================================================
# Sooqify Image Updater
# First-run settings: folder path, browser, sync credentials, developer-mode detection.
# =========================================================
# Developer: Yousef Alhamzy

from __future__ import annotations

import json
import os
from typing import Any

try:
    import keyring
    import keyring.errors
    _KEYRING_AVAILABLE = True
except ImportError:  # Optional dependency - we carry on without it (see _save_token_fallback_file below).
    keyring = None
    _KEYRING_AVAILABLE = False

APP_NAME = "SooqifyImageUpdater"
_KEYRING_SERVICE = APP_NAME
_KEYRING_USERNAME = "SyncToken"

# Entering "yousef" (any case) as the operator name on first run enables developer mode automatically.
DEVELOPER_NAME_TRIGGER = "yousef"

# Security note: SyncToken is never stored here - it lives in the OS secret store
# (Windows Credential Manager / macOS Keychain / Linux Secret Service) via the keyring
# library, and is only read when actually needed. If keyring is unavailable on the
# machine (rare), we fall back to a separate file with restricted permissions instead
# of embedding it as plaintext in the regular config file.
DEFAULT_CONFIG: dict[str, Any] = {
    "RootFolder": "",
    "Browser": "chrome",           # chrome / brave / edge
    "OperatorName": "",
    "DeveloperMode": False,
    "SyncEnabled": False,
    "SyncServerUrl": "",
    "BatchLimit": 0,                # 0 = no limit (the recommended default)
    "SoundOnComplete": True,
    "SetupCompleted": False,
    "Headless": False,              # True = run the browser without a visible window (required on headless Linux servers)
}


def get_config_dir() -> str:
    """App settings folder (outside the install folder, survives updates)."""
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def get_config_path() -> str:
    return os.path.join(get_config_dir(), "config.json")


def get_log_dir() -> str:
    return os.path.join(get_config_dir(), "logs")


def get_browser_profile_dir() -> str:
    """
    A browser profile owned by the app only (completely empty on first run, no
    extensions or personal data). Created once and kept as-is between runs - you log
    into Sooqify inside it exactly once, and it persists automatically afterward thanks
    to using a persistent context, with no copying of the operator's real browser
    profile whatsoever.
    """
    path = os.path.join(get_config_dir(), "browser_profile")
    os.makedirs(path, exist_ok=True)
    return path


def _fallback_token_path() -> str:
    return os.path.join(get_config_dir(), ".sync_token")


def _save_token_fallback_file(token: str) -> None:
    """Fallback only, for when keyring is unavailable on the machine - a separate file with restricted permissions where possible."""
    path = _fallback_token_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write(token)
    try:
        os.chmod(path, 0o600)  # No practical effect on Windows, but no harm either.
    except OSError:
        pass


def _load_token_fallback_file() -> str:
    path = _fallback_token_path()
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _delete_token_fallback_file() -> None:
    path = _fallback_token_path()
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def save_sync_token(token: str) -> None:
    """Save the sync token to the OS secret store - never as plaintext in the config file."""
    token = token or ""
    if _KEYRING_AVAILABLE:
        try:
            if token:
                keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, token)
            else:
                try:
                    keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
                except keyring.errors.PasswordDeleteError:
                    pass
            _delete_token_fallback_file()  # If one was previously saved to the fallback, clean it up after keyring succeeds.
            return
        except keyring.errors.KeyringError:
            pass  # Fall through to the fallback below if keyring genuinely failed (not just unavailable).
    if token:
        _save_token_fallback_file(token)
    else:
        _delete_token_fallback_file()


def load_sync_token() -> str:
    if _KEYRING_AVAILABLE:
        try:
            value = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
            if value:
                return value
        except keyring.errors.KeyringError:
            pass
    return _load_token_fallback_file()


def load_config() -> dict[str, Any]:
    """Read the saved settings (without the secret token), merging in any new default key an older version didn't have."""
    path = get_config_path()
    config = dict(DEFAULT_CONFIG)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                stored.pop("SyncToken", None)  # Backward compat: if an old version wrote it here, don't read it back from here.
                stored.pop("BrowserProfilePath", None)  # Old setting, removed - no longer used.
                config.update(stored)
        except (json.JSONDecodeError, OSError):
            pass  # Corrupted settings file - fall back to defaults instead of breaking the app.
    return config


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    """Save settings (the secret token goes to the secret store, not this file); recompute DeveloperMode from the entered name."""
    config = dict(config)
    if "SyncToken" in config:
        save_sync_token(config.pop("SyncToken"))

    merged = load_config()
    merged.update(config)
    merged["DeveloperMode"] = (
        merged.get("OperatorName", "").strip().lower() == DEVELOPER_NAME_TRIGGER
    )
    with open(get_config_path(), "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return merged


def load_config_with_token() -> dict[str, Any]:
    """Same as load_config but with the secret token attached (internal use only - e.g. SyncClient), never sent to the frontend."""
    config = load_config()
    config["SyncToken"] = load_sync_token()
    return config


def is_setup_complete(config: dict[str, Any] | None = None) -> bool:
    config = config or load_config()
    return bool(config.get("SetupCompleted") and config.get("RootFolder"))
