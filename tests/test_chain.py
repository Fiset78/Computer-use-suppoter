"""이어서 하기: handoff 결과를 받아 새 실행을 이어 붙이고, 통계를 합치고, 한도에서 멈춘다."""
import asyncio

import pytest

from agent import chain
from agent.loop import RunResult
from tests.test_batch import FakeExecutor, FakeRecorder


def fake_agent(script):
    """script: 실행마다 돌려줄 (status, progress, next_goal). 받은 목표를 기록한다."""
    goals = []

    def run(goal, executor, recorder, stats):
        status, progress, next_goal = script[len(goals)]
        goals.append(goal)
        stats.status, stats.progress, stats.next_goal = status, progress, next_goal
        stats.steps, stats.actions, stats.input_tokens = 30, 10, 1000
        stats.final = "끝" if status == "done" else ""
    return run, goals


def test_chains_until_done():
    run, goals = fake_agent([("handoff", "이동 확인", "점프 확인"), ("handoff", "점프 확인", "인벤토리"),
                             ("done", "", "")])
    rec = FakeRecorder()
    total = chain.run_chain(run, "마인크래프트 조작 테스트", FakeExecutor(), rec, max_parts=5)
    assert total.status == "done" and total.final == "끝"
    assert (total.steps, total.actions, total.input_tokens) == (90, 30, 3000)
    assert goals[0] == "마인크래프트 조작 테스트"
    assert "[이어서 하기 2/5]" in goals[1] and "이동 확인" in goals[1] and "점프 확인" in goals[1]
    assert "마인크래프트 조작 테스트" in goals[2] and "인벤토리" in goals[2]
    assert [d["part"] for k, d in rec.events if k == "handoff"] == [1, 2]


def test_stops_at_max_parts():
    run, goals = fake_agent([("handoff", "a", "b")] * 3)
    total = chain.run_chain(run, "목표", FakeExecutor(), FakeRecorder(), max_parts=2)
    assert len(goals) == 2 and total.status == "max_steps" and "남은 일: b" in total.final


def test_single_part_without_handoff():
    run, goals = fake_agent([("done", "", "")])
    total = chain.run_chain(run, "목표", FakeExecutor(), FakeRecorder(), max_parts=1)
    assert len(goals) == 1 and total.status == "done"


def test_sdk_handoff_tool_and_step_note(monkeypatch):
    pytest.importorskip("claude_agent_sdk")
    import config
    from agent import sdk_loop

    monkeypatch.setattr(config, "MAX_STEPS", 30)
    stats = RunResult(steps=28)
    tools = sdk_loop._Tools(FakeExecutor(), FakeRecorder(), stats, assist=None, handoff=True)
    assert [t.name for t in tools.build()] == ["computer", "handoff"]
    out = asyncio.run(tools.computer({"actions": [{"action": "key", "text": "w"}]}))
    assert out["content"][0]["text"] == "[단계 28/30 · 남은 단계 2]"
    asyncio.run(tools.handoff_tool({"progress": "이동 확인", "next_goal": "점프"}))
    assert tools.handoff == {"progress": "이동 확인", "next_goal": "점프"}
    after = asyncio.run(tools.computer({"actions": [{"action": "key", "text": "w"}]}))
    assert after["is_error"]  # 넘긴 뒤에는 조작하지 않는다
    assert "handoff" in sdk_loop.system_prompt(None, False, handoff=True)
    assert "handoff" not in sdk_loop.system_prompt(None, False, handoff=False)
