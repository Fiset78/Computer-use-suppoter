"""SDK 엔진의 computer 도구 배치 규칙: 순서 실행, 첫 실패 후 미실행, 자동 스크린샷, MCP 형식 변환."""
import pytest

from agent import batch


class FakeRecorder:
    def __init__(self):
        self.events = []

    def event(self, kind, **data):
        self.events.append((kind, data))


class FakeExecutor:
    def __init__(self, fail_on=(), raise_exc=None):
        self.fail_on = set(fail_on)
        self.raise_exc = raise_exc
        self.ran = []

    def run(self, name, inp):
        self.ran.append((name, inp))
        if self.raise_exc is not None:
            raise self.raise_exc
        if name in self.fail_on:
            raise RuntimeError("boom")
        if name == "screenshot":
            return [self.screenshot_block("screenshot")]
        return "OK"

    def screenshot_block(self, label):
        return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": label}}


def test_runs_in_order_and_appends_screenshot():
    ex = FakeExecutor()
    out = batch.run_batch([{"action": "left_click", "coordinate": [1, 2]}, {"action": "type", "text": "a"}],
                          ex, FakeRecorder())
    assert [n for n, _ in ex.ran] == ["left_click", "type"]
    assert ex.ran[0][1] == {"coordinate": [1, 2]}  # action 필드는 빠진다
    assert out.executed == 2 and not out.is_error
    assert out.content[-1] == {"type": "image", "data": "auto", "mimeType": "image/png"}


def test_no_auto_screenshot_after_observe():
    out = batch.run_batch([{"action": "key", "text": "Return"}, {"action": "screenshot"}],
                          FakeExecutor(), FakeRecorder())
    images = [b for b in out.content if b["type"] == "image"]
    assert [b["data"] for b in images] == ["screenshot"]


def test_stops_after_first_failure():
    ex = FakeExecutor(fail_on={"left_click"})
    out = batch.run_batch([{"action": "key", "text": "a"}, {"action": "left_click"}, {"action": "type", "text": "x"}],
                          ex, FakeRecorder())
    assert [n for n, _ in ex.ran] == ["key", "left_click"]
    assert out.executed == 2 and out.errors == 1 and out.is_error
    assert batch.NOT_EXECUTED in out.content[-1]["text"]
    assert all(b["type"] == "text" for b in out.content)  # 실패하면 자동 스크린샷 없음


def test_unknown_action_is_error():
    ex = FakeExecutor()
    out = batch.run_batch([{"action": "fly"}], ex, FakeRecorder())
    assert out.is_error and ex.ran == []


def test_failsafe_propagates():
    import pyautogui
    ex = FakeExecutor(raise_exc=pyautogui.FailSafeException())
    with pytest.raises(pyautogui.FailSafeException):
        batch.run_batch([{"action": "left_click"}], ex, FakeRecorder())


def test_schema_lists_all_17_actions():
    assert len(batch.ACTIONS) == 17
    enum = batch.COMPUTER_TOOL_SCHEMA["properties"]["actions"]["items"]["properties"]["action"]["enum"]
    assert set(enum) == set(batch.ACTIONS)
