"""게임 창만 캡처/조작하기: 창 고르기, 캡처 영역 좌표 변환, 입력 전 포커스 되돌리기."""
from types import SimpleNamespace

import pytest

from actions.assist import AssistTools
from actions.executor import Executor
from perception import capture, window
from perception.window import WindowInfo, pick_window
from safety.guard import Guard
from test_game import Backend, Screen as FakeScreen


def w(hwnd, title, width=800, height=600):
    return WindowInfo(hwnd, title, (0, 0, width, height))


def test_pick_window_prefers_largest_match_and_skips_terminal():
    wins = [
        w(1, "Minecraft 1.21.1", 1536, 864),
        w(2, "Minecraft Launcher", 1000, 600),
        w(3, "uv run main.py Minecraft에서 나무 캐줘", 2000, 1000),  # 명령줄에 게임 이름이 들어간 터미널
        w(4, "minecraft - 최소화됨", 0, 0),
        w(5, "Minecraft* 1.21.1 - 싱글플레이", 1600, 900),
    ]
    assert pick_window(wins, "minecraft").hwnd == 5
    assert pick_window(wins, "minecraft", exclude_hwnds={5}).hwnd == 1
    assert pick_window(wins, "") is None
    assert pick_window(wins, "notepad") is None


def test_screen_region_maps_coordinates_inside_window(monkeypatch):
    monkeypatch.setattr(capture.mss, "mss", lambda: SimpleNamespace(monitors=[None, None]))
    s = capture.Screen(max_long_edge=1280, region=(100, 50, 2560, 1440))
    assert (s.shot_w, s.shot_h) == (1280, 720)
    assert s.to_screen(0, 0) == (100, 50)
    assert s.to_screen(640, 360) == (100 + 1280, 50 + 720)
    assert s.to_shot(100 + 1280, 50 + 720) == (640, 360)
    with pytest.raises(ValueError):
        capture.Screen(region=(0, 0, 0, 100))


class FocusRecorder:
    def __init__(self):
        self.events = []

    def event(self, kind, **data):
        self.events.append((kind, data))


@pytest.fixture
def desktop(monkeypatch):
    """가짜 Windows: 활성 창과 focus 호출 기록."""
    state = SimpleNamespace(fg=99, focus_calls=[], focus_ok=True)

    def focus(hwnd):
        state.focus_calls.append(hwnd)
        if state.focus_ok:
            state.fg = hwnd
        return state.focus_ok

    monkeypatch.setattr(window, "foreground", lambda: state.fg)
    monkeypatch.setattr(window, "focus", focus)
    return state


def make(focus_hwnd=7):
    b = Backend()
    ex = Executor(FakeScreen(), Guard(confirm=False), FocusRecorder(), action_delay=0, backend=b)
    ex.focus_hwnd = focus_hwnd
    return ex, b


def test_input_action_refocuses_target_window(desktop):
    ex, b = make()
    ex.run("left_mouse_down", {})
    assert desktop.focus_calls == [7]
    assert ex.recorder.events == [("refocus", {"ok": True})]
    ex.run("left_mouse_down", {})
    assert desktop.focus_calls == [7]  # 이미 활성 창이면 다시 부르지 않음


def test_observe_actions_do_not_steal_focus(desktop):
    ex, _ = make()
    ex.run("wait", {"duration": 0})
    assert desktop.focus_calls == []


def test_no_focus_target_means_no_focus_calls(desktop):
    ex, _ = make(focus_hwnd=None)
    ex.run("left_mouse_down", {})
    assert desktop.focus_calls == []


def test_refocus_failure_is_error_before_any_input(desktop):
    desktop.focus_ok = False
    ex, b = make()
    with pytest.raises(RuntimeError):
        ex.run("left_mouse_down", {})
    assert b.calls == []


def test_game_tools_refocus_too(desktop):
    ex, b = make()
    assist = AssistTools(ex, ["game"], counts_per_deg=10)
    assist.run("look", {"yaw": 1})
    assert desktop.focus_calls == [7]


def test_guard_prompt_returns_focus_after_answer(monkeypatch):
    calls = []
    g = Guard(confirm=True)
    g.after_prompt = lambda: calls.append("focus")
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    g.check_key(["alt", "f4"])
    assert calls == ["focus"]
