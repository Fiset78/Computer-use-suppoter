"""입력 백엔드와 Executor가 백엔드를 통해서만 입력하는지 검증한다 (가짜 모듈 사용)."""
import sys
import types

import pytest

from actions import backends
from actions.executor import Executor


# ---------- 가짜 pydirectinput (pydirectinput-rgx와 같은 이름의 함수) ----------
@pytest.fixture
def fake_pdi(monkeypatch):
    m = types.ModuleType("pydirectinput")
    m.calls = []

    class FailSafeException(Exception):
        pass

    m.FailSafeException = FailSafeException
    valid = {"ctrl", "shift", "alt", "win", "enter", "v", "w", "a", "A", "!", " "}
    m.is_valid_key = lambda k: k in valid
    for name in ("moveTo", "moveRel", "mouseDown", "mouseUp", "click", "scroll",
                 "keyDown", "keyUp", "hotkey", "typewrite"):
        setattr(m, name, (lambda n: lambda *a, **k: m.calls.append((n, a, k)))(name))
    m.position = lambda: (5, 6)
    monkeypatch.setitem(sys.modules, "pydirectinput", m)
    return m


def test_create_unknown_backend():
    with pytest.raises(ValueError):
        backends.create("xinput")


def test_directinput_scroll_is_in_notches_and_move_rel_is_relative(fake_pdi):
    b = backends.create("directinput")
    b.scroll(-3)
    b.move_rel(40, -10)
    assert ("scroll", (-3,), {}) in fake_pdi.calls
    assert ("moveRel", (40, -10), {"relative": True}) in fake_pdi.calls


def test_directinput_rejects_unknown_keys_before_pressing(fake_pdi):
    b = backends.create("directinput")
    with pytest.raises(ValueError, match="hangul"):
        b.hotkey("ctrl", "hangul")
    with pytest.raises(ValueError):
        b.write("한글")
    assert fake_pdi.calls == []


def test_directinput_write_uses_auto_shift(fake_pdi):
    backends.create("directinput").write("A !")
    assert fake_pdi.calls == [("typewrite", ("A !",), {"interval": 0.01, "auto_shift": True})]


def test_failsafe_registered_for_each_backend(fake_pdi):
    import pyautogui

    backends.create("pyautogui")
    backends.create("directinput")
    assert backends.is_failsafe(pyautogui.FailSafeException())
    assert backends.is_failsafe(fake_pdi.FailSafeException())
    assert not backends.is_failsafe(ValueError())


def test_pyautogui_rejects_unknown_key():
    with pytest.raises(ValueError):
        backends.create("pyautogui").hotkey("ctrl", "nosuchkey")


# ---------- Executor → 백엔드 ----------
class RecordingBackend(backends.InputBackend):
    name = "recording"

    def __init__(self, valid=("ctrl", "shift", "alt", "enter", "v", "a")):
        self.calls = []
        self.valid = set(valid)

    def move_to(self, x, y, duration=0.0):
        self.calls.append(("move_to", (x, y), {"duration": duration}))

    def key_down(self, key):
        self.calls.append(("key_down", (key,), {}))

    def key_up(self, key):
        self.calls.append(("key_up", (key,), {}))

    def click(self, button="left", clicks=1, interval=0.08):
        self.calls.append(("click", (button, clicks), {}))

    def scroll(self, notches):
        self.calls.append(("scroll", (notches,), {}))

    def mouse_down(self, button="left"):
        self.calls.append(("mouse_down", (button,), {}))

    def mouse_up(self, button="left"):
        self.calls.append(("mouse_up", (button,), {}))

    def hotkey(self, *keys):
        self.calls.append(("hotkey", keys, {}))

    def write(self, text, interval=0.01):
        self.calls.append(("write", (text,), {}))

    def is_valid_key(self, key):
        return key in self.valid


class FakeScreen:
    shot_w, shot_h = 1280, 720

    def in_bounds(self, x, y):
        return 0 <= x < self.shot_w and 0 <= y < self.shot_h

    def to_screen(self, x, y):
        return x * 2, y * 2


class AllowGuard:
    def check_key(self, combo):
        pass

    def check_text(self, text):
        pass


def make(backend=None):
    b = backend or RecordingBackend()
    return Executor(FakeScreen(), AllowGuard(), None, action_delay=0, backend=b), b


def names(calls):
    return [c[0] for c in calls]


def test_click_with_modifier_holds_and_releases_in_order():
    ex, b = make()
    ex.run("left_click", {"coordinate": [10, 20], "text": "ctrl+shift"})
    assert b.calls == [
        ("key_down", ("ctrl",), {}), ("key_down", ("shift",), {}),
        ("move_to", (20, 40), {"duration": 0.0}), ("click", ("left", 1), {}),
        ("key_up", ("shift",), {}), ("key_up", ("ctrl",), {}),
    ]


def test_unknown_modifier_rejected_before_any_input():
    ex, b = make()
    with pytest.raises(ValueError):
        ex.run("left_click", {"coordinate": [10, 20], "text": "ctrl+hyper"})
    assert b.calls == []


def test_horizontal_scroll_uses_shift_and_notches():
    ex, b = make()
    ex.run("scroll", {"coordinate": [1, 1], "scroll_direction": "right", "scroll_amount": 2})
    assert names(b.calls) == ["move_to", "key_down", "scroll", "key_up"]
    assert b.calls[2] == ("scroll", (-2,), {})


def test_drag_releases_mouse_even_if_move_fails():
    class Failing(RecordingBackend):
        def move_to(self, x, y, duration=0.0):
            super().move_to(x, y, duration)
            if duration:
                raise RuntimeError("move failed")

    ex, b = make(Failing())
    with pytest.raises(RuntimeError):
        ex.run("left_click_drag", {"start_coordinate": [0, 0], "coordinate": [5, 5]})
    assert names(b.calls)[-1] == "mouse_up"


def test_key_repeat_and_validation():
    ex, b = make()
    ex.run("key", {"text": "ctrl+a", "repeat": 2})
    assert b.calls == [("hotkey", ("ctrl", "a"), {})] * 2
    with pytest.raises(ValueError):
        ex.run("key", {"text": "Hangul"})


def test_ascii_type_goes_through_backend_write():
    ex, b = make()
    ex.run("type", {"text": "hello"})
    assert b.calls[0][0] == "write" and b.calls[0][1] == ("hello",)


def test_cursor_position_uses_backend(monkeypatch):
    ex, b = make()
    b.position = lambda: (200, 100)
    ex.screen.to_shot = lambda x, y: (x // 2, y // 2)
    assert ex.run("cursor_position", {}) == "X=100, Y=50"
