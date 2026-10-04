"""구독 남은 사용량: RateLimitEvent 정보 저장·합치기·표시 문구."""
import time
from types import SimpleNamespace

from agent import usage


def info(kind, util=None, status="allowed", resets=None):
    return SimpleNamespace(rate_limit_type=kind, utilization=util, status=status, resets_at=resets)


def test_merge_keeps_latest_per_type(tmp_path):
    f = tmp_path / "usage.json"
    store = usage.merge(usage.load(f), usage.from_info(info("five_hour", 0.2), now=1))
    store = usage.merge(store, usage.from_info(info("seven_day", 0.5), now=2))
    store = usage.merge(store, usage.from_info(info("five_hour", 0.4), now=3))
    usage.save(f, store)
    again = usage.load(f)
    assert again["five_hour"]["utilization"] == 0.4 and again["seven_day"]["checked_at"] == 2
    assert [e["type"] for e in usage.ordered(again)] == ["five_hour", "seven_day"]


def test_remaining_and_describe():
    now = time.time()
    e = usage.from_info(info("five_hour", 0.27, resets=now + 3600), now=now)
    assert abs(usage.remaining(e) - 0.73) < 1e-9
    assert usage.describe(e, now).startswith("남음 73% · ") and "초기화" in usage.describe(e, now)
    rejected = usage.from_info(info("seven_day", None, status="rejected"), now=now)
    assert usage.remaining(rejected) == 0.0
    unknown = usage.from_info(info("seven_day", None, status="allowed_warning"), now=now)
    assert usage.remaining(unknown) is None and usage.describe(unknown, now) == "거의 다 씀"
    past = usage.from_info(info("five_hour", 0.9, resets=now - 10), now=now)
    assert "초기화됨" in usage.describe(past, now)


def test_unknown_type_ignored_and_bad_file(tmp_path):
    assert usage.from_info(SimpleNamespace(rate_limit_type=None)) is None
    bad = tmp_path / "bad.json"
    bad.write_text("{깨진", encoding="utf-8")
    assert usage.load(bad) == {}


def test_sdk_loop_records_and_notifies(tmp_path, monkeypatch):
    import pytest
    pytest.importorskip("claude_agent_sdk")
    import config
    from agent import sdk_loop

    monkeypatch.setattr(config, "RUNS_DIR", str(tmp_path))
    seen = []
    monkeypatch.setattr(sdk_loop, "usage_listeners", [seen.append])
    store = sdk_loop.record_usage(info("five_hour", 0.1))
    assert store["five_hour"]["utilization"] == 0.1 and seen == [store]
    assert usage.load(tmp_path / "usage.json")["five_hour"]["utilization"] == 0.1


def test_from_get_usage():
    resp = {
        "subscription_type": "max",
        "rate_limits_available": True,
        "rate_limits": {
            "five_hour": {"utilization": 27.0, "resets_at": "2026-10-04T16:40:00Z"},
            "seven_day": {"utilization": 63.5, "resets_at": "2026-10-08T03:00:00+00:00"},
            "seven_day_opus": None,
            "model_scoped": [{"display_name": "Fable", "utilization": 10, "resets_at": None}],
            "extra_usage": {"is_enabled": False},
        },
    }
    store = usage.from_get_usage(resp, now=100)
    assert set(store) == {"five_hour", "seven_day", "model:Fable"}
    assert abs(usage.remaining(store["five_hour"]) - 0.73) < 1e-9
    assert store["seven_day"]["resets_at"] > 1.7e9 and store["seven_day"]["checked_at"] == 100
    assert usage.label("model:Fable") == "주간 (Fable)" and usage.label("five_hour") == "5시간 한도"
    assert usage.from_get_usage({"rate_limits_available": False, "rate_limits": None}) == {}


def test_fetch_usage_with_fake_client(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import pytest
    pytest.importorskip("claude_agent_sdk")
    import config
    from agent import sdk_loop

    monkeypatch.setattr(config, "RUNS_DIR", str(tmp_path))
    seen = []
    monkeypatch.setattr(sdk_loop, "usage_listeners", [seen.append])

    async def ok(req):
        assert req == {"subtype": "get_usage"}
        return {"rate_limits": {"five_hour": {"utilization": 40, "resets_at": None}}}

    async def broken(req):
        raise RuntimeError("get_usage is not supported in this context")

    good = SimpleNamespace(_query=SimpleNamespace(_send_control_request=ok))
    store = asyncio.run(sdk_loop.fetch_usage(good))
    assert abs(store["five_hour"]["utilization"] - 0.4) < 1e-9 and seen == [store]
    bad = SimpleNamespace(_query=SimpleNamespace(_send_control_request=broken))
    assert asyncio.run(sdk_loop.fetch_usage(bad)) is None
    assert usage.load(tmp_path / "usage.json")["five_hour"]["utilization"] == 0.4  # 실패해도 이전 값 유지
