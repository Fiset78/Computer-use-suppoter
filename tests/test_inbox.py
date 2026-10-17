"""실행 중 추가 지시: 접수 → 다음 도구 결과에 전달, 정지 말, 끝난 뒤 이어서 할 목표."""
import asyncio

import pytest

from agent import inbox as inbox_mod
from agent.inbox import MARKER, Inbox, as_block, follow_up_goal, is_stop_command
from agent.loop import RunResult
from tests.test_batch import FakeExecutor, FakeRecorder


def test_inbox_drain_once():
    box = Inbox()
    box.put("  점프도 해 봐 ")
    box.put("")
    assert len(box) == 1 and box.drain() == ["점프도 해 봐"] and box.drain() == []


@pytest.mark.parametrize("text,stop", [("멈춰", True), ("정지!", True), ("그만 해 줘.", True), ("그만해", True),
                                       ("Stop", True), ("멈춰서 주변을 둘러봐", False), ("앞으로 가", False)])
def test_stop_words(text, stop):
    assert is_stop_command(text) is stop


def test_block_and_follow_up():
    block = as_block(["점프", "인벤토리 열어"])
    assert block["text"].startswith(MARKER) and "- 점프" in block["text"]
    goal = follow_up_goal("메모장 열기", "열었습니다", ["저장도 해줘"])
    assert "메모장 열기" in goal and "열었습니다" in goal and "- 저장도 해줘" in goal


def test_sdk_tool_result_carries_instruction(monkeypatch):
    pytest.importorskip("claude_agent_sdk")
    from agent import sdk_loop

    box = Inbox()
    monkeypatch.setattr(sdk_loop, "inbox", box)
    rec = FakeRecorder()
    tools = sdk_loop._Tools(FakeExecutor(), rec, RunResult(), assist=None)
    box.put("오른쪽으로 돌아")
    out = asyncio.run(tools.computer({"actions": [{"action": "key", "text": "w"}]}))
    texts = [b["text"] for b in out["content"] if b["type"] == "text"]
    assert texts[0].startswith("[단계") and texts[-1].startswith(MARKER) and "오른쪽으로 돌아" in texts[-1]
    assert ("user_instruction", {"messages": ["오른쪽으로 돌아"]}) in rec.events
    again = asyncio.run(tools.computer({"actions": [{"action": "key", "text": "w"}]}))
    assert not any(MARKER in b.get("text", "") for b in again["content"])  # 한 번만 전달


def test_module_inbox_is_shared():
    assert isinstance(inbox_mod.inbox, Inbox)
