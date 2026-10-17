"""구독 사용량(남은 한도) 기록과 표시 (순수 모듈).

sdk 엔진 실행 중 Claude Code가 보내는 RateLimitEvent에서 한도 종류별 사용 비율과 초기화 시각을 받아
runs/usage.json에 남긴다. 실행 창은 이 값으로 '남은 사용량' 바를 그린다.
Claude Code는 한도 상태가 바뀔 때 이 정보를 보내므로, 값은 '마지막으로 확인한 시점' 기준이다.
"""
import json
import time
from datetime import datetime
from pathlib import Path

# 한도 종류 → 보이는 이름 (표시 순서도 이 순서)
LIMIT_NAMES = {
    "five_hour": "5시간 한도",
    "seven_day": "주간 한도",
    "seven_day_opus": "주간 (Opus)",
    "seven_day_sonnet": "주간 (Sonnet)",
    "overage": "추가 사용",
}
STATUS_NAMES = {"allowed": "여유", "allowed_warning": "거의 다 씀", "rejected": "한도 도달"}


def from_info(info, now: float | None = None) -> dict | None:
    """RateLimitInfo(또는 같은 필드를 가진 객체) → 저장용 dict. 한도 종류를 모르면 None."""
    kind = getattr(info, "rate_limit_type", None)
    if not kind:
        return None
    return {
        "type": kind,
        "status": getattr(info, "status", None),
        "utilization": getattr(info, "utilization", None),
        "resets_at": getattr(info, "resets_at", None),
        "checked_at": now if now is not None else time.time(),
    }


# get_usage 응답의 한도 창 (claude.ai 사용량 엔드포인트와 같은 값)
GET_USAGE_WINDOWS = ("five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet")


def _epoch(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def from_get_usage(response: dict, now: float | None = None) -> dict:
    """Claude Code의 get_usage 제어 요청 응답 → 한도 종류별 dict.
    utilization은 0~100(%)으로 오므로 0~1로 바꾼다. 한도 정보가 없으면 빈 dict."""
    now = now if now is not None else time.time()
    limits = (response or {}).get("rate_limits") or {}
    entries = {}

    def add(kind, window):
        if not isinstance(window, dict):
            return
        util = window.get("utilization")
        entries[kind] = {
            "type": kind,
            "status": None,
            "utilization": None if util is None else float(util) / 100.0,
            "resets_at": _epoch(window.get("resets_at")),
            "checked_at": now,
        }

    for kind in GET_USAGE_WINDOWS:
        add(kind, limits.get(kind))
    for item in limits.get("model_scoped") or []:
        if isinstance(item, dict) and item.get("display_name"):
            add(f"model:{item['display_name']}", item)
    return entries


def label(kind: str) -> str:
    if kind.startswith("model:"):
        return f"주간 ({kind[6:]})"
    return LIMIT_NAMES.get(kind, kind)


def merge(store: dict, entry: dict | None) -> dict:
    """한도 종류별 최신 값만 남긴다."""
    if entry:
        store = {**store, entry["type"]: entry}
    return store


def remaining(entry: dict) -> float | None:
    """남은 비율 0.0~1.0. 사용 비율을 모르면 상태로 짐작하고, 그래도 모르면 None."""
    util = entry.get("utilization")
    if util is not None:
        return max(0.0, min(1.0, 1.0 - float(util)))
    if entry.get("status") == "rejected":
        return 0.0
    return None


def _when(ts: float, now: float) -> str:
    t, n = datetime.fromtimestamp(ts), datetime.fromtimestamp(now)
    return t.strftime("%H:%M") if t.date() == n.date() else t.strftime("%m/%d %H:%M")


def describe(entry: dict, now: float | None = None) -> str:
    """바 옆에 붙일 설명. 예: '남음 73% · 16:40 초기화'"""
    now = now if now is not None else time.time()
    rest = remaining(entry)
    parts = [f"남음 {rest * 100:.0f}%" if rest is not None else STATUS_NAMES.get(entry.get("status"), "정보 없음")]
    resets = entry.get("resets_at")
    if resets:
        parts.append(f"{_when(resets, now)} 초기화" if resets > now else "초기화됨 (다음 실행 때 갱신)")
    return " · ".join(parts)


def ordered(store: dict) -> list[dict]:
    known = [store[k] for k in LIMIT_NAMES if k in store]
    return known + [v for k, v in store.items() if k not in LIMIT_NAMES]


def load(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(path: Path, store: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
