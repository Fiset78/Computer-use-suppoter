"""computer 툴셋(computer_toolset_20260801)의 17개 멤버 도구를 실제 마우스/키보드 동작으로 실행한다.

- 모든 좌표는 '스크린샷 좌표'로 들어오고, Screen.to_screen()으로 실제 화면 좌표로 바꿔서 적용한다.
- 반환값: 텍스트(str) 또는 content 블록 리스트(스크린샷/zoom 이미지).
- 실패하면 예외를 던진다. 루프가 is_error로 Claude에게 보고한다.
- 실제 입력은 교체 가능한 입력 백엔드(actions/backends.py)가 보낸다.
"""
import time
from contextlib import contextmanager

import pyperclip

from actions.backends import InputBackend, PyAutoGuiBackend, StopRequested
from actions.keys import parse_combo, parse_modifiers
from perception.capture import Screen, to_image_block
from safety.guard import Guard


class Executor:
    def __init__(self, screen: Screen, guard: Guard, recorder=None, action_delay: float = 0.4,
                 backend: InputBackend | None = None, stop_check=None):
        self.screen = screen
        self.input = backend if backend is not None else PyAutoGuiBackend()
        self.guard = guard
        self.recorder = recorder
        self.action_delay = action_delay
        self.last_shot = None  # Claude에게 마지막으로 보낸 전체 스크린샷 (wait_for_change의 기준)
        self.stop_check = stop_check  # 참을 돌려주면 다음 행동 전에 멈춘다 (실행 창의 정지 버튼)

    def check_stop(self) -> None:
        if self.stop_check is not None and self.stop_check():
            raise StopRequested("사용자가 정지했습니다.")

    # ---------- 공통 유틸 ----------
    def _point(self, coord) -> tuple[int, int]:
        x, y = coord
        if not self.screen.in_bounds(x, y):
            raise ValueError(
                f"좌표 {coord}가 화면 밖입니다 (스크린샷 크기 {self.screen.shot_w}x{self.screen.shot_h})."
            )
        return self.screen.to_screen(x, y)

    def _move_if(self, coord) -> None:
        if coord is not None:
            self.input.move_to(*self._point(coord))

    @contextmanager
    def _hold(self, modifiers: list[str]):
        self.input.check_keys(modifiers)  # 하나라도 모르는 키면 아무것도 누르기 전에 거부
        pressed = []
        try:
            for k in modifiers:
                self.input.key_down(k)
                pressed.append(k)
            yield
        finally:
            for k in reversed(pressed):
                self.input.key_up(k)

    def image_block(self, img, label: str) -> dict:
        """전체 화면 스크린샷을 기록하고 이미지 블록으로 만든다."""
        self.last_shot = img
        if self.recorder:
            self.recorder.image(img, label)
        return to_image_block(img)

    def screenshot_block(self, label: str = "shot") -> dict:
        return self.image_block(self.screen.capture(), label)

    # ---------- 디스패치 ----------
    def run(self, name: str, inp: dict):
        self.check_stop()
        handler = getattr(self, f"do_{name}", None)
        if handler is None:
            raise NotImplementedError(f"구현되지 않은 도구입니다: {name}")
        result = handler(inp)
        if name not in ("screenshot", "zoom", "cursor_position", "wait"):
            time.sleep(self.action_delay)  # UI가 반응할 시간
        return result

    # ---------- 관찰 ----------
    def do_screenshot(self, inp):
        return [self.screenshot_block("screenshot")]

    def do_zoom(self, inp):
        img = self.screen.capture_region(inp["region"])
        if self.recorder:
            self.recorder.image(img, "zoom")
        return [to_image_block(img)]

    def do_cursor_position(self, inp):
        sx, sy = self.input.position()
        x, y = self.screen.to_shot(sx, sy)
        return f"X={x}, Y={y}"

    # ---------- 마우스 ----------
    def _click(self, inp, button="left", clicks=1):
        with self._hold(parse_modifiers(inp.get("text"))):
            self._move_if(inp.get("coordinate"))
            self.input.click(button=button, clicks=clicks, interval=0.08)
        return "OK"

    def do_left_click(self, inp):
        return self._click(inp)

    def do_right_click(self, inp):
        return self._click(inp, button="right")

    def do_middle_click(self, inp):
        return self._click(inp, button="middle")

    def do_double_click(self, inp):
        return self._click(inp, clicks=2)

    def do_triple_click(self, inp):
        return self._click(inp, clicks=3)

    def do_left_click_drag(self, inp):
        start = self._point(inp["start_coordinate"])
        end = self._point(inp["coordinate"])
        with self._hold(parse_modifiers(inp.get("text"))):
            self.input.move_to(*start)
            self.input.mouse_down("left")
            try:
                self.input.move_to(*end, duration=0.4)  # 너무 빠르면 드래그로 인식 안 되는 앱이 있음
            finally:
                self.input.mouse_up("left")
        return "OK"

    def do_mouse_move(self, inp):
        self.input.move_to(*self._point(inp["coordinate"]), duration=0.1)
        return "OK"

    def do_left_mouse_down(self, inp):
        self.input.mouse_down("left")
        return "OK"

    def do_left_mouse_up(self, inp):
        self.input.mouse_up("left")
        return "OK"

    def do_scroll(self, inp):
        direction = inp["scroll_direction"]
        amount = int(inp.get("scroll_amount", 3))
        mods = parse_modifiers(inp.get("text"))
        self._move_if(inp.get("coordinate"))
        if direction in ("left", "right"):
            # 가로 휠은 앱마다 지원이 들쭉날쭉하므로 Shift+휠로 처리
            if "shift" not in mods:
                mods = mods + ["shift"]
            clicks = amount if direction == "left" else -amount
        else:
            clicks = amount if direction == "up" else -amount
        with self._hold(mods):
            self.input.scroll(clicks)
        return "OK"

    # ---------- 키보드 ----------
    def do_type(self, inp):
        text = inp["text"]
        self.guard.check_text(text)
        if text.isascii():
            self.input.write(text, interval=0.01)
        else:
            # 한글 등 비ASCII 문자는 키 입력으로 넣을 수 없으므로 클립보드 붙여넣기 사용
            try:
                backup = pyperclip.paste()
            except Exception:
                backup = None
            pyperclip.copy(text)
            self.input.hotkey("ctrl", "v")
            time.sleep(0.3)  # 붙여넣기가 끝나기 전에 클립보드를 되돌리면 옛 내용이 들어갈 수 있다
            if backup is not None:
                pyperclip.copy(backup)
        return "OK"

    def do_key(self, inp):
        combo = parse_combo(inp["text"])
        self.input.check_keys(combo)
        self.guard.check_key(combo)
        for _ in range(int(inp.get("repeat", 1))):
            self.input.hotkey(*combo)
        return "OK"

    def do_hold_key(self, inp):
        combo = parse_combo(inp["text"])
        self.input.check_keys(combo)
        self.guard.check_key(combo)
        duration = min(float(inp["duration"]), 300)
        with self._hold(combo):
            time.sleep(duration)
        return "OK"

    def do_wait(self, inp):
        time.sleep(min(float(inp.get("duration", 1)), 300))
        return "OK"
