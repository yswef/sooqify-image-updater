# =========================================================
# Sooqify Image Updater - تهيئة الاختبارات
# التطبيق يستورد وحداته بأسماء مسطّحة (import config / import work_log) لأن main.py
# يضيف مجلد app لـsys.path عند التشغيل. نكرّر نفس الشيء هنا حتى تعمل الاختبارات
# على **نفس** مسارات الاستيراد التي يعمل بها التطبيق فعلياً، لا على نسخة مختلفة.
# =========================================================

import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


@pytest.fixture
def isolated_config_dir(tmp_path, monkeypatch):
    """
    يعزل مجلد إعدادات التطبيق داخل tmp_path، فلا يلمس أي اختبار ملفات %APPDATA%
    الحقيقية للمستخدم (سجل عمله الفعلي) لا بقراءة ولا بكتابة.
    """
    import config as app_config

    target = tmp_path / "config_dir"
    target.mkdir()
    monkeypatch.setattr(app_config, "get_config_dir", lambda: str(target))
    return str(target)


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """إيقاع الطلبات الهادئ (0.3s) لا داعي له بالاختبارات - يُلغى حتى تبقى سريعة."""
    import sync_client

    monkeypatch.setattr(sync_client, "_sleep", lambda seconds: None)
