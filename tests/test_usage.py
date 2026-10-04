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
