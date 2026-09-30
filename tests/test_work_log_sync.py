# =========================================================
# Sooqify Image Updater - اختبارات سجل العمل والمزامنة
#
# الاختبار المحوري هنا هو `test_reconcile_recovers_records_the_watermark_would_lose`:
# يعيد إنتاج حادثة AlphaCode الحقيقية (3800 سجلاً على الخادم مقابل 2476 محلياً،
# 1324 مفقوداً بصمت والمزامنة تقول "نجحت") ويثبت أن المصالحة الكاملة تستعيدها
# وتُعلن الفارق بدل ابتلاعه.
# =========================================================

import json

import pytest

import sync_client as sync_client_module
import work_log


# ---------------------------------------------------------
# خادم مزامنة وهمي يحاكي عقد sync.php
# ---------------------------------------------------------

class FakeSyncServer:
    """
    يحاكي sync.php: `pull` بـsince="" يرجّع كل شيء، و`push` يخزّن بالمفتاح.
    `since_is_lossy` يحاكي العيب الحقيقي: سحب تزايدي يرجّع ما بعد العلامة المائية فقط.
    """

    def __init__(self, items=None, fail_push_keys=(), block_403_after=None, members=None):
        self.items = dict(items or {})
        self.pull_calls = []
        self.push_calls = []
        self.whoami_calls = []
        self.fail_push_keys = set(fail_push_keys)
        self.block_403_after = block_403_after
        # يحاكي جدولي members/member_aliases: {الاسم أو المرادف (lower): display_name}
        self.members = {k.lower(): v for k, v in (members or {}).items()}

    def __call__(self, action, payload=None, method="POST"):
        if action == "pull":
            self.pull_calls.append(payload)
            since = (payload or {}).get("since") or ""
            if since:
                # محاكاة العيب الحقيقي: بعلامة مائية يرجّع الخادم ما بعدها فقط،
                # فكل ما هو أقدم منها يُفقد نهائياً ولا يعود السحب ينظر خلفه.
                items = {
                    key: item for key, item in self.items.items()
                    if str(item.get("timestamp") or "") >= since
                }
            else:
                items = dict(self.items)
            return {"items": items, "server_time": "2026-09-22T03:00:00"}, None
        if action == "push":
            key = payload["key"]
            self.push_calls.append(key)
            if self.block_403_after is not None and len(self.push_calls) > self.block_403_after:
                return None, "sync_blocked_403"
            if key in self.fail_push_keys:
                return None, "boom"
            self.items[key] = payload["product"]
            return {"success": True}, None
        if action == "whoami":
            key = str(payload.get("key") or "")
            self.whoami_calls.append(key)
            display = self.members.get(key.lower())
            if display is None:
                return {"success": False, "error": "Not found"}, "Not found"
            return {"success": True, "member": {"display_name": display, "role": ""}}, None
        raise AssertionError(f"unexpected action {action}")


def _client(monkeypatch, server):
    client = sync_client_module.SyncClient("https://example.test/store", "TOKEN")
    monkeypatch.setattr(client, "_call", server)
    return client


def _unit(item_id, user="يوسف", date="2026-09-22", status=work_log.STATUS_DONE, quantity=1):
    return work_log.make_work_unit(
        user=user, date=date, item_id=item_id, status=status,
        quantity=quantity, timestamp=f"{date} 10:00:00",
    )


# ---------------------------------------------------------
# الشكل الموحَّد
# ---------------------------------------------------------

def test_unit_shape_carries_the_agreed_fields():
    unit = _unit("SC-1", quantity=5)
    for field in ("source", "user", "date", "item_type", "item_id", "status"):
        assert field in unit
    assert unit["record_kind"] == "work_unit"
    assert unit["source"] == "image_updater"
    assert unit["date"] == "2026-09-22"


def test_key_is_deterministic_so_re_pushing_never_double_counts():
    assert work_log.work_unit_key(_unit("SC-1")) == work_log.work_unit_key(_unit("SC-1"))
    assert work_log.work_unit_key(_unit("SC-1")) != work_log.work_unit_key(_unit("SC-2"))


def test_key_is_not_underscore_prefixed():
    """مفتاح يبدأ بـ"_" تستثنيه مصالحة AlphaCode من الرفع، فلن تصل وحدات العمل أبداً."""
    assert not work_log.work_unit_key(_unit("SC-1")).startswith("_")


# ---------------------------------------------------------
# السجل المحلي
# ---------------------------------------------------------

def test_units_are_appended_and_read_back(isolated_config_dir):
    assert work_log.append_unit(_unit("SC-1"))
    assert work_log.append_unit(_unit("SC-2"))
    units, corrupt = work_log.load_units()
    assert corrupt == 0
    assert sorted(u["item_id"] for u in units) == ["SC-1", "SC-2"]


def test_append_is_line_wise_so_a_torn_write_costs_one_unit_not_the_file(isolated_config_dir):
    """
    الفارق الجوهري عن "ملف JSON واحد يُقرأ ويُكتب كاملاً": سطر تالف يفقد وحدة واحدة
    ويُعلَن، بينما ملف JSON تالف يفقد السجل كله ويرجع فارغاً بصمت.
    """
    work_log.append_unit(_unit("SC-1"))
    with open(work_log.get_work_log_path(), "a", encoding="utf-8") as handle:
        handle.write('{"record_kind": "work_unit", "item_id": "SC-torn"\n')  # سطر مبتور
    work_log.append_unit(_unit("SC-3"))

    units, corrupt = work_log.load_units()
    assert corrupt == 1                                    # التلف مُعلَن، لا مبتلع
    assert sorted(u["item_id"] for u in units) == ["SC-1", "SC-3"]   # الباقي سليم


def test_corrupt_lines_are_counted_not_silently_dropped(isolated_config_dir):
    with open(work_log.get_work_log_path(), "w", encoding="utf-8") as handle:
        handle.write("not json at all\n")
        handle.write(json.dumps({"record_kind": "something_else"}) + "\n")
    units, corrupt = work_log.load_units()
    assert units == []
    assert corrupt == 2


def test_sync_state_write_is_atomic_and_round_trips(isolated_config_dir):
    assert work_log.save_sync_state({"last_reconcile_at": "2026-09-22T10:00:00", "last_delta": 3})
    state = work_log.load_sync_state()
    assert state["last_reconcile_at"] == "2026-09-22T10:00:00"
    assert state["last_delta"] == 3
    # لا يبقى أي ملف مؤقت بعد الكتابة الذرّية.
    import os
    assert not [n for n in os.listdir(isolated_config_dir) if n.endswith(".tmp")]


# ---------------------------------------------------------
# المزامنة - الشفاء الذاتي وفقدان السجلات
# ---------------------------------------------------------

def test_reconcile_recovers_records_the_watermark_would_lose(isolated_config_dir, monkeypatch):
    """
    إعادة إنتاج حادثة الإنتاج الحقيقية بمقياس مصغّر:
    الخادم يحمل سجلات لا يحملها الجهاز، والسحب التزايدي بعلامة مائية متقدّمة لن
    ينظر خلفه أبداً فيفقدها بصمت. المصالحة الكاملة (since="") تستعيدها كلها.
    """
    # محلياً: وحدتان فقط. على الخادم: نفس الوحدتين + 5 وحدات أقدم من زميل آخر.
    local_ids = ["SC-90", "SC-91"]
    for item_id in local_ids:
        work_log.append_unit(_unit(item_id, user="يوسف", date="2026-09-22"))

    server_items = {}
    for item_id in local_ids:
        unit = _unit(item_id, user="يوسف", date="2026-09-22")
        server_items[work_log.work_unit_key(unit)] = unit
    for index in range(5):
        unit = _unit(f"SC-{index}", user="معتز", date="2026-08-20")
        server_items[work_log.work_unit_key(unit)] = unit

    server = FakeSyncServer(server_items)
    client = _client(monkeypatch, server)

    summary = client.reconcile_work_units()

    # السحب كان كاملاً لا تزايدياً - هذا هو جوهر الشفاء الذاتي.
    assert server.pull_calls == [{"since": ""}]
    assert summary["success"] is True
    assert summary["local_count"] == 2
    assert summary["remote_count"] == 7
    assert summary["delta"] == 5          # الفارق مُعلَن صراحةً
    assert summary["pulled_in"] == 5      # واستُعيد فعلاً

    # وبعد المصالحة صار المحلي مطابقاً للخادم.
    units, _ = work_log.load_units()
    assert len(work_log.units_by_key(units)) == 7
    assert {u["user"] for u in units} == {"يوسف", "معتز"}


def test_pull_stays_full_even_after_a_previous_reconcile(isolated_config_dir, monkeypatch):
    """
    الحارس الحقيقي ضد العودة للسحب التزايدي: بعد مصالحة سابقة (وبالتالي وجود طابع
    زمني محفوظ)، يجب أن يبقى السحب `since=""`. لو استُخدمت العلامة المائية هنا
    لاختفت السجلات الأقدم منها - وهي بالضبط الـ1324 سجلاً التي فُقدت بالإنتاج.
    """
    old_unit = _unit("OLD", user="معتز", date="2026-08-01")
    old_unit["timestamp"] = "2026-08-01 09:00:00"
    server = FakeSyncServer({work_log.work_unit_key(old_unit): old_unit})
    client = _client(monkeypatch, server)

    work_log.save_sync_state({"last_reconcile_at": "2026-09-22T02:33:09"})

    summary = client.reconcile_work_units()

    assert server.pull_calls == [{"since": ""}], (
        "السحب صار تزايدياً - السجلات الأقدم من العلامة المائية ستُفقد بصمت"
    )
    assert summary["remote_count"] == 1
    assert summary["pulled_in"] == 1


def test_reconcile_is_additive_and_never_deletes_local_work(isolated_config_dir, monkeypatch):
    """المصالحة إضافية بحتة: وحدة محلية لا يعرفها الخادم تبقى وتُرفع، لا تُمسح."""
    work_log.append_unit(_unit("LOCAL-ONLY"))
    server = FakeSyncServer({})
    client = _client(monkeypatch, server)

    summary = client.reconcile_work_units()

    assert summary["pushed"] == 1
    units, _ = work_log.load_units()
    assert [u["item_id"] for u in units] == ["LOCAL-ONLY"]
    assert work_log.work_unit_key(_unit("LOCAL-ONLY")) in server.items


def test_second_reconcile_pushes_nothing_new(isolated_config_dir, monkeypatch):
    """المفتاح الحتمي يجعل المصالحة idempotent - لا رفع مكرر ولا عدّ مزدوج."""
    work_log.append_unit(_unit("SC-1"))
    server = FakeSyncServer({})
    client = _client(monkeypatch, server)

    client.reconcile_work_units()
    pushes_after_first = len(server.push_calls)
    second = client.reconcile_work_units()

    assert len(server.push_calls) == pushes_after_first
    assert second["pushed"] == 0
    assert second["delta"] == 0
    assert second["in_sync"] is True


def test_a_failed_pull_is_never_reported_as_success(isolated_config_dir, monkeypatch):
    """فشل السحب يجب أن يُعلَن - ادّعاء النجاح هنا هو الفشل الصامت بعينه."""
    def failing(action, payload=None, method="POST"):
        return None, "Connection refused"

    client = sync_client_module.SyncClient("https://example.test", "TOKEN")
    monkeypatch.setattr(client, "_call", failing)

    summary = client.reconcile_work_units()
    assert summary["success"] is False
    assert summary["in_sync"] is False
    assert summary["error"] == "Connection refused"
    assert work_log.load_sync_state()["last_error"] == "Connection refused"


def test_pull_without_items_field_is_an_error_not_an_empty_server(isolated_config_dir, monkeypatch):
    """
    استجابة بلا "items" لو عوملت كقاموس فارغ لبدا الخادم خالياً والمزامنة "متطابقة"
    وهي لم تقرأ شيئاً - فشل صامت يفقد كل شيء.
    """
    def weird(action, payload=None, method="POST"):
        return {"ok": True}, None

    client = sync_client_module.SyncClient("https://example.test", "TOKEN")
    monkeypatch.setattr(client, "_call", weird)

    summary = client.reconcile_work_units()
    assert summary["success"] is False
    assert "items" in summary["error"]


def test_in_sync_is_false_while_anything_is_still_missing(isolated_config_dir, monkeypatch):
    """"متطابقة" لا تُكتب إلا والفارق صفر ولا رفع فاشل ولا باقٍ - وإلا فهي كذبة."""
    work_log.append_unit(_unit("SC-1"))
    work_log.append_unit(_unit("SC-2"))
    failing_key = work_log.work_unit_key(_unit("SC-2"))
    server = FakeSyncServer({}, fail_push_keys=[failing_key])
    client = _client(monkeypatch, server)

    summary = client.reconcile_work_units()
    assert summary["success"] is True      # السحب نجح
    assert summary["push_failed"] == 1
    assert summary["in_sync"] is False     # لكن المزامنة ليست متطابقة


def test_push_batch_is_capped_and_the_remainder_is_announced(isolated_config_dir, monkeypatch):
    """دفعة أولى ضخمة لا تُغرق الاستضافة؛ والباقي يُعلَن بدل أن يبدو منتهياً."""
    monkeypatch.setattr(sync_client_module, "MAX_PUSH_PER_RECONCILE", 3)
    for index in range(10):
        work_log.append_unit(_unit(f"SC-{index}"))
    server = FakeSyncServer({})
    client = _client(monkeypatch, server)

    summary = client.reconcile_work_units()
    assert summary["pushed"] == 3
    assert summary["remaining_to_push"] == 7
    assert summary["in_sync"] is False


def test_host_block_403_stops_pushing_immediately(isolated_config_dir, monkeypatch):
    """حظر 403 يوقف الطلبات فوراً بدل إطالة الحظر، ويُعلن ما تبقّى."""
    for index in range(6):
        work_log.append_unit(_unit(f"SC-{index}"))
    server = FakeSyncServer({}, block_403_after=2)
    client = _client(monkeypatch, server)

    summary = client.reconcile_work_units()
    assert len(server.push_calls) == 3      # نجحت اثنتان ثم توقّف عند أول حظر
    assert summary["pushed"] == 2
    assert summary["remaining_to_push"] > 0
    assert summary["in_sync"] is False


# ---------------------------------------------------------
# المصالحة التلقائية (الشفاء الذاتي بلا زر يدوي)
# ---------------------------------------------------------

def test_auto_reconcile_runs_on_a_fresh_machine(isolated_config_dir, monkeypatch):
    server = FakeSyncServer({})
    client = _client(monkeypatch, server)
    assert client.auto_reconcile_if_due() is not None
    assert server.pull_calls == [{"since": ""}]


def test_auto_reconcile_skips_inside_the_interval(isolated_config_dir, monkeypatch):
    import datetime

    work_log.save_sync_state({
        "last_reconcile_at": datetime.datetime.now().isoformat(timespec="seconds"),
    })
    server = FakeSyncServer({})
    client = _client(monkeypatch, server)
    assert client.auto_reconcile_if_due() is None
    assert server.pull_calls == []


def test_auto_reconcile_runs_again_after_the_interval(isolated_config_dir, monkeypatch):
    import datetime

    stale = datetime.datetime.now() - datetime.timedelta(
        hours=sync_client_module.FULL_RECONCILE_INTERVAL_HOURS + 1
    )
    work_log.save_sync_state({"last_reconcile_at": stale.isoformat(timespec="seconds")})
    server = FakeSyncServer({})
    client = _client(monkeypatch, server)
    assert client.auto_reconcile_if_due() is not None


def test_a_corrupt_timestamp_forces_a_reconcile_rather_than_skipping(isolated_config_dir, monkeypatch):
    work_log.save_sync_state({"last_reconcile_at": "not-a-timestamp"})
    server = FakeSyncServer({})
    client = _client(monkeypatch, server)
    assert client.auto_reconcile_if_due() is not None


# ---------------------------------------------------------
# تسجيل العمل المنجز
# ---------------------------------------------------------

def test_work_is_recorded_locally_even_when_sync_is_off(isolated_config_dir):
    """
    أهم ضمانة ضد ضياع العمل: الشبكة أو الإعداد لا يمنعان التسجيل المحلي. السلوك
    السابق كان الدفع المباشر بلا سجل محلي - فأي فشل شبكة = عمل ضائع من كل تقرير.
    """
    client = sync_client_module.SyncClient("", "")
    assert client.configured is False

    outcome = client.record_images_updated("SC-7", 5, "يوسف")
    assert outcome["recorded"] is True
    assert outcome["pushed"] is False

    units, _ = work_log.load_units()
    assert units[0]["item_id"] == "SC-7"
    assert units[0]["quantity"] == 5
    assert units[0]["user"] == "يوسف"


def test_work_recorded_while_offline_is_pushed_by_the_next_reconcile(isolated_config_dir, monkeypatch):
    """سيناريو كامل: عمل أثناء انقطاع الشبكة ثم عودتها - لا شيء يضيع."""
    offline = sync_client_module.SyncClient("", "")
    offline.record_images_updated("SC-OFFLINE", 3, "معتز")

    server = FakeSyncServer({})
    online = _client(monkeypatch, server)
    summary = online.reconcile_work_units()

    assert summary["pushed"] == 1
    assert any(item["item_id"] == "SC-OFFLINE" for item in server.items.values())


def test_record_pushes_immediately_when_sync_works(isolated_config_dir, monkeypatch):
    server = FakeSyncServer({})
    client = _client(monkeypatch, server)

    outcome = client.record_images_updated("SC-8", 4, "يوسف")
    assert outcome["recorded"] is True and outcome["pushed"] is True
    # التاريخ يؤخذ من ساعة الجهاز وقت التسجيل، فلا يُثبَّت بالاختبار (وإلا سقط عند
    # تغيّر اليوم أثناء التشغيل - وهذا ما حدث فعلاً).
    today, _ = work_log.now_parts()
    assert server.push_calls == [work_log.work_unit_key(_unit("SC-8", date=today))]


def test_a_failed_push_still_keeps_the_local_record(isolated_config_dir, monkeypatch):
    def failing(action, payload=None, method="POST"):
        return None, "Connection refused"

    client = sync_client_module.SyncClient("https://example.test", "TOKEN")
    monkeypatch.setattr(client, "_call", failing)

    outcome = client.record_images_updated("SC-9", 2, "يوسف")
    assert outcome["recorded"] is True
    assert outcome["pushed"] is False
    units, _ = work_log.load_units()
    assert [u["item_id"] for u in units] == ["SC-9"]


# ---------------------------------------------------------
# ربط الهوية عبر جدول أعضاء الخادم (whoami / member_aliases)
# ---------------------------------------------------------

def test_operator_name_is_resolved_to_the_server_canonical_name(isolated_config_dir, monkeypatch):
    """
    الحل الصحيح لربط الهوية: الخادم يعرف المرادفات بجدول member_aliases، فنسأله
    بدل أن نخمّن أن "yousef" هي "يوسف" - والتخمين ممنوع صراحةً.
    """
    server = FakeSyncServer({}, members={"yousef": "يوسف"})
    client = _client(monkeypatch, server)

    client.record_images_updated("SC-1", 3, "yousef")

    units, _ = work_log.load_units()
    assert units[0]["user"] == "يوسف"


def test_identity_is_cached_so_the_server_is_asked_once(isolated_config_dir, monkeypatch):
    server = FakeSyncServer({}, members={"yousef": "يوسف"})
    client = _client(monkeypatch, server)

    for index in range(4):
        client.record_images_updated(f"SC-{index}", 1, "yousef")

    assert server.whoami_calls == ["yousef"]   # نداء واحد فقط، لا نداء لكل منتج


def test_an_unknown_operator_still_gets_their_work_recorded(isolated_config_dir, monkeypatch):
    """فشل التحقق لا يوقف العمل ولا يفقده - يُسجَّل بالاسم المحلي كما هو."""
    server = FakeSyncServer({}, members={})
    client = _client(monkeypatch, server)

    outcome = client.record_images_updated("SC-1", 2, "اسم غير مسجّل")
    assert outcome["recorded"] is True
    units, _ = work_log.load_units()
    assert units[0]["user"] == "اسم غير مسجّل"


def test_identity_resolution_is_skipped_entirely_when_sync_is_off(isolated_config_dir):
    client = sync_client_module.SyncClient("", "")
    assert client.resolve_operator_identity("yousef") == "yousef"
