"""SDK 엔진 연결부: 도구 등록, 핸들러 통계, 긴급 정지, 결과 상태 변환. (CLI는 띄우지 않음)"""
import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("claude_agent_sdk")

from actions.executor import Executor  # noqa: E402
from agent import batch, sdk_loop  # noqa: E402
from agent.loop import RunResult  # noqa: E402
from tests.test_batch import FakeExecutor, FakeRecorder  # noqa: E402


def test_executor_implements_every_action():
    for name in batch.ACTIONS:
        assert hasattr(Executor, f"do_{name}"), name


def test_computer_handler_counts_actions():
    stats = RunResult()
    tools = sdk_loop._Tools(FakeExecutor(fail_on={"type"}), FakeRecorder(), stats, assist=None)
    assert [t.name for t in tools.build()] == ["computer"]
    out = asyncio.run(tools.computer({"actions": [{"action": "key", "text": "a"}, {"action": "type", "text": "b"}]}))
    assert out["is_error"] is True
    assert (stats.actions, stats.action_errors) == (2, 1)


def test_failsafe_sets_abort():
    import pyautogui
    tools = sdk_loop._Tools(FakeExecutor(raise_exc=pyautogui.FailSafeException()), FakeRecorder(),
                            RunResult(), assist=None)
    out = asyncio.run(tools.computer({"actions": [{"action": "left_click"}]}))
    assert out["is_error"] and isinstance(tools.abort, pyautogui.FailSafeException)
    # 정지 후에는 아무것도 실행하지 않는다
    tools.executor.raise_exc = None
    asyncio.run(tools.computer({"actions": [{"action": "key", "text": "a"}]}))
    assert len(tools.executor.ran) == 1


@pytest.mark.parametrize("subtype,is_error,stop,expected", [
    ("success", False, "end_turn", "done"),
    ("success", False, "max_tokens", "truncated"),
    ("success", True, None, "error"),
    ("error_max_turns", True, None, "max_steps"),
    ("error_during_execution", True, None, "error"),
])
def test_map_status(subtype, is_error, stop, expected):
    msg = SimpleNamespace(subtype=subtype, is_error=is_error, stop_reason=stop)
    assert sdk_loop.map_status(msg) == expected


def test_apply_usage():
    stats = RunResult()
    sdk_loop.apply_usage(stats, {"input_tokens": 5, "output_tokens": 7,
                                 "cache_read_input_tokens": 100, "cache_creation_input_tokens": 3})
    assert (stats.input_tokens, stats.output_tokens, stats.cache_read_tokens, stats.cache_write_tokens) == (5, 7, 100, 3)
