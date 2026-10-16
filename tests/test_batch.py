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


def test_schema_lists_all_actions():
    assert len(batch.ACTIONS) == 18 and "look" in batch.ACTIONS  # 툴셋 17개 + 게임용 look
    enum = batch.COMPUTER_TOOL_SCHEMA["properties"]["actions"]["items"]["properties"]["action"]["enum"]
    assert set(enum) == set(batch.ACTIONS)


def test_look_sends_relative_moves_in_small_steps():
    from actions.executor import Executor
    from safety.guard import Guard

    class Backend:
        def __init__(self):
            self.moves = []

        def position(self):
            return (960, 540)  # 게임이 마우스를 잡고 있어 커서가 가운데 고정

        def move_rel(self, dx, dy):
            self.moves.append((dx, dy))

    b = Backend()
    ex = Executor(screen=None, guard=Guard(confirm=False), backend=b, action_delay=0)
    assert ex.do_look({"delta": [250, -70]}).startswith("OK")
    assert sum(m[0] for m in b.moves) == 250 and sum(m[1] for m in b.moves) == -70
    assert all(abs(m[0]) <= Executor.LOOK_STEP and abs(m[1]) <= Executor.LOOK_STEP for m in b.moves)


def test_look_warns_when_cursor_is_free():
    from actions.executor import Executor
    from safety.guard import Guard

    class FreeCursor:  # 메뉴가 열려 커서가 실제로 따라 움직이는 상황
        def __init__(self):
            self.x, self.y = 500, 500

        def position(self):
            return (self.x, self.y)

        def move_rel(self, dx, dy):
            self.x += dx
            self.y += dy

    ex = Executor(screen=None, guard=Guard(confirm=False), backend=FreeCursor(), action_delay=0)
    out = ex.do_look({"delta": [600, 0]})
    assert out.startswith("주의") and "600px" in out
