"""computer 툴셋(computer_toolset_20260801)의 17개 멤버 도구를 실제 마우스/키보드 동작으로 실행한다.

- 모든 좌표는 '스크린샷 좌표'로 들어오고, Screen.to_screen()으로 실제 화면 좌표로 바꿔서 적용한다.
- 반환값: 텍스트(str) 또는 content 블록 리스트(스크린샷/zoom 이미지).
- 실패하면 예외를 던진다. 루프가 is_error로 Claude에게 보고한다.
"""
import sys
import time
from contextlib import contextmanager

import pyautogui
import pyperclip

from actions.keys import parse_combo, parse_modifiers
from perception.capture import Screen, to_image_block
from safety.guard import Guard

pyautogui.FAILSAFE = True  # 마우스를 왼쪽 위 모서리로 옮기면 긴급 정지
pyautogui.PAUSE = 0.05      # pyautogui 호출 사이 기본 간격

# Windows에서 pyautogui.scroll(1)은 휠 한 칸의 1/120만 움직인다
WHEEL_UNIT = 120 if sys.platform == "win32" else 1


class Executor:
    def __init__(self, screen: Screen, guard: Guard, recorder=None, action_delay: float = 0.4):
        self.screen = screen
        self.guard = guard
        self.recorder = recorder
        self.action_delay = action_delay

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
            pyautogui.moveTo(*self._point(coord))

    @contextmanager
    def _hold(self, modifiers: list[str]):
        for k in modifiers:
            pyautogui.keyDown(k)
        try:
            yield
        finally:
            for k in reversed(modifiers):
                pyautogui.keyUp(k)

    def screenshot_block(self, label: str = "shot") -> dict:
        img = self.screen.capture()
        if self.recorder:
            self.recorder.image(img, label)
        return to_image_block(img)

    # ---------- 디스패치 ----------
    def run(self, name: str, inp: dict):
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
        sx, sy = pyautogui.position()
        x, y = self.screen.to_shot(sx, sy)
        return f"X={x}, Y={y}"

    # ---------- 마우스 ----------
    def _click(self, inp, button="left", clicks=1):
        with self._hold(parse_modifiers(inp.get("text"))):
            self._move_if(inp.get("coordinate"))
            pyautogui.click(button=button, clicks=clicks, interval=0.08)
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
            pyautogui.moveTo(*start)
            pyautogui.mouseDown(button="left")
            pyautogui.moveTo(*end, duration=0.4)  # 너무 빠르면 드래그로 인식 안 되는 앱이 있음
            pyautogui.mouseUp(button="left")
        return "OK"

    def do_mouse_move(self, inp):
        pyautogui.moveTo(*self._point(inp["coordinate"]), duration=0.1)
        return "OK"

    def do_left_mouse_down(self, inp):
        pyautogui.mouseDown(button="left")
        return "OK"

    def do_left_mouse_up(self, inp):
        pyautogui.mouseUp(button="left")
        return "OK"

    def do_scroll(self, inp):
        direction = inp["scroll_direction"]
        amount = int(inp.get("scroll_amount", 3))
        mods = parse_modifiers(inp.get("text"))
        self._move_if(inp.get("coordinate"))
        if direction in ("left", "right"):
            # Windows에서 pyautogui 가로 스크롤이 불안정하므로 Shift+휠로 처리
            if "shift" not in mods:
                mods = mods + ["shift"]
            clicks = amount if direction == "left" else -amount
        else:
            clicks = amount if direction == "up" else -amount
        with self._hold(mods):
            pyautogui.scroll(clicks * WHEEL_UNIT)
        return "OK"

    # ---------- 키보드 ----------
    def do_type(self, inp):
        text = inp["text"]
        self.guard.check_text(text)
        if text.isascii():
            pyautogui.write(text, interval=0.01)
        else:
            # 한글 등 비ASCII 문자는 pyautogui.write로 입력되지 않으므로 클립보드 붙여넣기 사용
            try:
                backup = pyperclip.paste()
            except Exception:
                backup = None
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
            if backup is not None:
                pyperclip.copy(backup)
        return "OK"

    def do_key(self, inp):
        combo = parse_combo(inp["text"])
        self.guard.check_key(combo)
        for _ in range(int(inp.get("repeat", 1))):
            pyautogui.hotkey(*combo)
        return "OK"

    def do_hold_key(self, inp):
        combo = parse_combo(inp["text"])
        self.guard.check_key(combo)
        duration = min(float(inp["duration"]), 300)
        with self._hold(combo):
            time.sleep(duration)
        return "OK"

    def do_wait(self, inp):
        time.sleep(min(float(inp.get("duration", 1)), 300))
        return "OK"
