"""벤치마크 결과 집계. GUI 의존성이 없는 순수 모듈이라 Linux에서도 테스트할 수 있다.

레코드 하나 = 과제 1회 실행 결과 dict:
    {"task": str, "trial": int, "success": bool | None, "status": str,
     "steps": int, "actions": int, "action_errors": int,
     "input_tokens": int, "output_tokens": int, "cache_read_tokens": int,
     "cache_write_tokens": int, "seconds": float, ...}
success가 None이면 판정하지 않은(건너뛴) 실행으로 보고 성공률 계산에서 뺀다.
"""
METRIC_KEYS = ("steps", "actions", "action_errors", "input_tokens", "output_tokens",
               "cache_read_tokens", "cache_write_tokens", "cleared_tool_uses", "pruned_images", "seconds",
               "think_seconds", "action_seconds")


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate(records: list[dict]) -> dict:
    """레코드 묶음 하나의 성공률과 평균 지표를 계산한다."""
    judged = [r for r in records if r.get("success") is not None]
    successes = [r for r in judged if r["success"]]
    out = {
        "runs": len(records),
        "judged": len(judged),
        "successes": len(successes),
        "success_rate": len(successes) / len(judged) if judged else None,
    }
    for key in METRIC_KEYS:
        out[f"avg_{key}"] = _mean([r[key] for r in records if r.get(key) is not None])
    # 성공한 실행만의 평균 단계 수: 실패가 max_steps까지 끌고 가 평균을 부풀리는 것을 분리해서 본다
    out["avg_steps_success"] = _mean([r["steps"] for r in successes if r.get("steps") is not None])
    return out


def summarize(records: list[dict]) -> dict:
    """전체 요약과 과제별 요약. 과제 순서는 처음 등장한 순서를 따른다."""
    by_task: dict[str, list[dict]] = {}
    for r in records:
        by_task.setdefault(r["task"], []).append(r)
    return {
        "overall": aggregate(records),
        "tasks": {task: aggregate(rs) for task, rs in by_task.items()},
    }


def _fmt(value, kind: str) -> str:
    if value is None:
        return "-"
    if kind == "rate":
        return f"{value * 100:.0f}%"
    if kind == "int":
        return f"{value:,.0f}"
    return f"{value:.1f}"


COLUMNS = [
    ("과제", None, None),
    ("성공", "success_rate", "rate"),
    ("실행", "runs", "int"),
    ("단계", "avg_steps", "float"),
    ("행동", "avg_actions", "float"),
    ("입력토큰", "avg_input_tokens", "int"),
    ("캐시읽기", "avg_cache_read_tokens", "int"),
    ("캐시쓰기", "avg_cache_write_tokens", "int"),
    ("출력토큰", "avg_output_tokens", "int"),
    ("시간(s)", "avg_seconds", "float"),
]


def format_table(summary: dict) -> str:
    """터미널 출력용 표."""
    rows = [[name] + [_fmt(agg[key], kind) for _, key, kind in COLUMNS[1:]]
            for name, agg in summary["tasks"].items()]
    rows.append(["(전체)"] + [_fmt(summary["overall"][key], kind) for _, key, kind in COLUMNS[1:]])
    header = [title for title, _, _ in COLUMNS]
    widths = [max(len(str(row[i])) for row in rows + [header]) for i in range(len(header))]
    lines = ["  ".join(str(c).ljust(w) for c, w in zip(header, widths))]
    lines.append("  ".join("-" * w for w in widths))
    lines += ["  ".join(str(c).ljust(w) for c, w in zip(row, widths)) for row in rows]
    return "\n".join(lines)
