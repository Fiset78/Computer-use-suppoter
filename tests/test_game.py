"""게임 보조 도구(look, look_at, hold), 시점 계산, 긴급 정지 단축키, release_all 검증."""
import math
import threading

import pytest

from actions import backends, camera
from actions.assist import AssistTools, backend_warning
from actions.executor import Executor
from safety import killswitch


@pytest.fixture(autouse=True)
def _reset_killswitch():
    killswitch.reset()
    yield
    killswitch.reset()


# ---------- 시점 계산 (순수 함수) ----------
def test_center_needs_no_turn():
    assert camera.shot_to_angles(640, 360, 1280, 720, 70) == (0.0, 0.0)


def test_top_edge_is_half_vertical_fov():
    yaw, pitch = camera.shot_to_angles(640, 0, 1280, 720, 70)
    assert yaw == 0.0 and pitch == pytest.approx(35.0)


def test_right_edge_uses_horizontal_fov():
    yaw, pitch = camera.shot_to_angles(1280, 360, 1280, 720, 70)
    hfov = 2 * math.degrees(math.atan(math.tan(math.radians(35)) * 1280 / 720))
    assert yaw == pytest.approx(hfov / 2) and pitch == 0.0


def test_left_and_down_are_negative():
    yaw, pitch = camera.shot_to_angles(100, 700, 1280, 720, 70)
    assert yaw < 0 and pitch < 0


def test_angles_to_counts_signs():
    # 오른쪽 위를 보려면 마우스는 오른쪽(+x), 위(-y)로
    assert camera.angles_to_counts(10, 5, 6.667) == (67, -33)
    with pytest.raises(ValueError):
        camera.angles_to_counts(1, 1, 0)


@pytest.mark.parametrize("total,parts", [(100, 7), (-55, 4), (0, 3), (3, 10)])
def test_split_counts_sums_exactly(total, parts):
    out = camera.split_counts(total, parts)
    assert len(out) == parts and sum(out) == total
    assert max(out) - min(out) <= 1


def test_chunk_moves_limits_step():
    moves = camera.chunk_moves(500, -130, max_step=120)
    assert sum(m[0] for m in moves) == 500 and sum(m[1] for m in moves) == -130
    assert all(abs(x) <= 120 and abs(y) <= 120 for x, y in moves)
    assert camera.chunk_moves(0, 0) == [(0, 0)]


# ---------- 긴급 정지 ----------
def test_vk_code():
    assert killswitch.vk_code("F12") == 0x7B
    assert killswitch.vk_code("f1") == 0x70
    assert killswitch.vk_code("pause") == 0x13
    with pytest.raises(ValueError):
        killswitch.vk_code("w")  # 게임에서 쓰는 키는 긴급 정지 키로 못 씀


def test_check_and_sleep_raise_after_trigger():
    killswitch.check()
    killswitch.trigger()
    with pytest.raises(killswitch.EmergencyStop):
        killswitch.check()
    with pytest.raises(KeyboardInterrupt):  # Ctrl+C와 같은 경로로 처리된다
        killswitch.sleep(5)


def test_sleep_wakes_up_when_triggered_from_other_thread():
    threading.Timer(0.05, killswitch.trigger).start()
    with pytest.raises(killswitch.EmergencyStop):
        killswitch.sleep(5)  # 5초를 다 기다리지 않는다


def test_start_hotkey_is_noop_off_windows():
    killswitch.trigger()
    assert killswitch.start_hotkey("f12") is None  # Linux에서는 감시 스레드 없음
    assert not killswitch.triggered()  # 시작할 때 이전 정지 상태를 지운다
    assert "F12" not in killswitch.stop_hint(None)


# ---------- release_all ----------
def test_release_all_lifts_held_keys_and_buttons():
    import pyautogui

    b = backends.create("pyautogui")
    b.key_down("a")
    b.key_down("ctrl")
    b.mouse_down("left")
    b.key_up("ctrl")
    pyautogui.calls.clear()
    assert b.release_all() == ["left", "a"]
    assert [c[0] for c in pyautogui.calls] == ["mouseUp", "keyUp"]
    assert b.release_all() == []


# ---------- game 도구 ----------
class Backend(backends.InputBackend):
    name = "directinput"

    def __init__(self):
        self.calls = []

    def move_rel(self, dx, dy):
        self.calls.append(("move_rel", dx, dy))

    def key_down(self, key):
        self.calls.append(("key_down", key))

    def key_up(self, key):
        self.calls.append(("key_up", key))

    def mouse_down(self, button="left"):
        self.calls.append(("mouse_down", button))

    def mouse_up(self, button="left"):
        self.calls.append(("mouse_up", button))

    def is_valid_key(self, key):
        return key in {"w", "ctrl", "shift", "space"}


class Screen:
    shot_w, shot_h = 1280, 720

    def in_bounds(self, x, y):
        return 0 <= x < self.shot_w and 0 <= y < self.shot_h


class Guard:
    def __init__(self):
        self.checked = []

    def check_key(self, combo):
        self.checked.append(combo)

    def check_text(self, text):
        pass


def make():
    b = Backend()
    ex = Executor(Screen(), Guard(), None, action_delay=0, backend=b)
    return AssistTools(ex, ["game"], game_fov=70, counts_per_deg=10), b


def moved(calls):
    return (sum(c[1] for c in calls if c[0] == "move_rel"), sum(c[2] for c in calls if c[0] == "move_rel"))


def test_game_tool_defs():
    assist, _ = make()
    assert [t["name"] for t in assist.tool_defs()] == ["look", "look_at", "hold", "move_item"]
    assert "look_at" in assist.prompt_hints()


def test_look_turns_by_counts_and_clamps():
    assist, b = make()
    out = assist.run("look", {"yaw": 30, "pitch": -10})
    assert moved(b.calls) == (300, 100)  # 아래를 보려면 마우스는 아래(+y)로
    assert all(abs(c[1]) <= 120 for c in b.calls)
    assert "+30.0°" in out
    b.calls.clear()
    assist.run("look", {"pitch": 200})
    assert moved(b.calls) == (0, -900)  # pitch는 90도로 제한


def test_look_at_center_does_nothing_and_rejects_outside():
    assist, b = make()
    assist.run("look_at", {"coordinate": [640, 360]})
    assert b.calls == []
    with pytest.raises(ValueError):
        assist.run("look_at", {"coordinate": [1280, 10]})


def test_look_at_matches_camera_math():
    assist, b = make()
    assist.run("look_at", {"coordinate": [900, 200]})
    yaw, pitch = camera.shot_to_angles(900, 200, 1280, 720, 70)
    assert moved(b.calls) == camera.angles_to_counts(yaw, pitch, 10)


def test_hold_presses_together_and_releases_in_reverse():
    assist, b = make()
    out = assist.run("hold", {"keys": ["w", "Control_L"], "mouse": ["left"], "duration": 0.1,
                              "look": {"yaw": 9}})
    kinds = [c for c in b.calls if c[0] != "move_rel"]
    assert kinds == [("key_down", "w"), ("key_down", "ctrl"), ("mouse_down", "left"),
                     ("mouse_up", "left"), ("key_up", "ctrl"), ("key_up", "w")]
    assert moved(b.calls) == (90, 0)
    assert len([c for c in b.calls if c[0] == "move_rel"]) > 1  # 시간에 걸쳐 나눠 돌림
    assert assist.executor.guard.checked == [["w", "ctrl"]]
    assert "0.1초" in out


def test_hold_validates_before_pressing():
    assist, b = make()
    with pytest.raises(ValueError):
        assist.run("hold", {"keys": ["w", "hangul"], "duration": 1})
    with pytest.raises(ValueError):
        assist.run("hold", {"mouse": ["side"], "duration": 1})
    with pytest.raises(ValueError):
        assist.run("hold", {"duration": 1})
    assert b.calls == []


def test_hold_releases_on_emergency_stop():
    assist, b = make()
    threading.Timer(0.05, killswitch.trigger).start()
    with pytest.raises(killswitch.EmergencyStop):
        assist.run("hold", {"keys": ["w"], "mouse": ["left"], "duration": 10})
    assert b.calls[-2:] == [("mouse_up", "left"), ("key_up", "w")]


def test_tools_refuse_to_start_after_emergency_stop():
    assist, b = make()
    killswitch.trigger()
    with pytest.raises(killswitch.EmergencyStop):
        assist.run("look", {"yaw": 10})
    with pytest.raises(killswitch.EmergencyStop):
        assist.executor.run("key", {"text": "w"})
    assert b.calls == []


def test_backend_warning():
    assert backend_warning(["game"], "pyautogui")
    assert backend_warning(["game"], "directinput") is None
    assert backend_warning(["uia"], "pyautogui") is None


# ---------- 인벤토리 클릭 ----------
class GuiBackend(Backend):
    click_settle = 0.0
    click_hold = 0.01

    def move_to(self, x, y, duration=0.0):
        self.calls.append(("move_to", x, y))

    def click(self, button="left", clicks=1, interval=0.08):
        self.calls.append(("click", button, clicks))


class ScaledScreen(Screen):
    def to_screen(self, x, y):
        return x * 2, y * 2


def make_gui(hold=0.01):
    b = GuiBackend()
    b.click_hold = hold
    ex = Executor(ScaledScreen(), Guard(), None, action_delay=0, backend=b)
    return AssistTools(ex, ["game"]), ex, b


def test_click_hold_presses_down_and_up_separately():
    _, ex, b = make_gui()
    ex.run("double_click", {"coordinate": [10, 20]})
    assert b.calls == [("move_to", 20, 40), ("mouse_down", "left"), ("mouse_up", "left"),
                       ("mouse_down", "left"), ("mouse_up", "left")]


def test_no_click_hold_keeps_single_click_call():
    _, ex, b = make_gui(hold=0)
    ex.run("right_click", {"coordinate": [10, 20]})
    assert b.calls == [("move_to", 20, 40), ("click", "right", 1)]


@pytest.mark.parametrize("mode,expected", [
    ("all", [((2, 4), "left"), ((20, 40), "left")]),
    ("half", [((2, 4), "right"), ((20, 40), "left")]),
    ("one", [((2, 4), "left"), ((20, 40), "right"), ((2, 4), "left")]),
])
def test_move_item_clicks_pick_then_place(mode, expected):
    assist, _, b = make_gui()
    out = assist.run("move_item", {"from": [1, 2], "to": [10, 20], "mode": mode})
    got = []
    pos = None
    for c in b.calls:
        if c[0] == "move_to":
            pos = (c[1], c[2])
        elif c[0] == "mouse_down":
            got.append((pos, c[1]))
    assert got == expected
    assert not any(c[0] == "move_to" and len(c) > 3 for c in b.calls)  # 드래그(누른 채 이동) 없음
    assert "(1,2) → (10,20)" in out


def test_move_item_validates_before_clicking():
    assist, _, b = make_gui()
    with pytest.raises(ValueError):
        assist.run("move_item", {"from": [1, 2], "to": [5000, 20]})
    with pytest.raises(ValueError):
        assist.run("move_item", {"from": [1, 2], "to": [3, 4], "mode": "stack"})
    assert b.calls == []


def test_backend_click_timing_defaults_and_overrides(fake_pdi=None):
    assert backends.create("pyautogui").click_hold == 0.0
    b = backends.create("pyautogui", click_settle=0.1, click_hold=-1)
    assert b.click_settle == 0.1 and b.click_hold == 0.0
