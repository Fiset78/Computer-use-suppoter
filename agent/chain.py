"""이어서 하기 (handoff). 한 번의 실행은 최대 MAX_STEPS 단계라서, 긴 작업은 Claude가 단계가 거의 다 찼을 때
handoff 도구로 '지금까지 한 일'과 '다음에 할 일'을 넘기고, 여기서 그 내용으로 새 실행을 이어 붙인다.
새 실행은 이전 스크린샷을 들고 가지 않으므로 대화가 가벼워진다. 최대 이어 붙이는 횟수는 config.MAX_CHAIN.
"""
from dataclasses import fields

from agent.loop import RunResult

# 실행마다 더하는 통계 (나머지 필드는 마지막 실행 값을 쓴다)
SUMMED = ("steps", "actions", "action_errors", "input_tokens", "output_tokens", "cache_read_tokens",
          "cache_write_tokens", "cleared_tool_uses", "pruned_images", "think_seconds", "action_seconds")


def compose_goal(original: str, progress: str, next_goal: str, part: int, max_parts: int) -> str:
    """이어 받는 실행의 목표 문장."""
    return (
        f"[이어서 하기 {part}/{max_parts}] 이전 실행이 단계 한도에 닿아 작업을 넘겨받았습니다.\n\n"
        f"원래 목표:\n{original}\n\n"
        f"지금까지 한 일:\n{progress.strip() or '(기록 없음)'}\n\n"
        f"이번에 할 일:\n{next_goal.strip()}\n\n"
        "화면을 먼저 확인하고, 이미 끝난 일은 다시 하지 마세요."
    )


def add_stats(total: RunResult, part: RunResult) -> None:
    for f in fields(RunResult):
        if f.name in SUMMED:
            setattr(total, f.name, getattr(total, f.name) + getattr(part, f.name))
        elif f.name not in ("next_goal", "progress"):
            setattr(total, f.name, getattr(part, f.name))


def run_chain(run_agent, goal: str, executor, recorder, max_parts: int,
              stats: RunResult | None = None) -> RunResult:
    """run_agent를 실행하고, 결과가 handoff면 넘겨받은 내용으로 max_parts번까지 이어서 실행한다.
    stats를 넘기면 매 실행이 끝날 때마다 합계를 채워 넣는다 (중간에 멈춰도 그때까지의 합계가 남음)."""
    total = stats if stats is not None else RunResult()
    current = goal
    for part in range(1, max(1, max_parts) + 1):
        result = RunResult()
        try:
            run_agent(current, executor, recorder, stats=result)
        finally:
            add_stats(total, result)
        if result.status != "handoff":
            return total
        recorder.event("handoff", part=part, progress=result.progress, next_goal=result.next_goal)
        if part >= max_parts:
            total.status = "max_steps"
            total.final = (f"이어서 하기 한도({max_parts}번)에 닿아 멈췄습니다.\n"
                           f"지금까지 한 일: {result.progress}\n남은 일: {result.next_goal}")
            return total
        print(f"\n===== 이어서 하기 {part + 1}/{max_parts} =====\n다음에 할 일: {result.next_goal}")
        current = compose_goal(goal, result.progress, result.next_goal, part + 1, max_parts)
    return total
