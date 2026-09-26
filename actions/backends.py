"""입력 백엔드 (로드맵 7단계). 마우스/키보드 입력을 실제로 보내는 부분을 교체할 수 있게 한다.

- pyautogui   : 일반 데스크톱 앱용 (기본값)
- directinput : 게임용. pydirectinput-rgx로 SendInput + 스캔 코드를 보낸다.
                DirectX 게임(마인크래프트 등)은 가상 키 코드 입력을 무시하는 경우가 많아서 필요하다.

Executor와 보조 도구는 이 인터페이스로만 입력을 보낸다. 키 이름은 pyautogui 기준(actions/keys.py)이고,
백엔드가 모르는 키는 조용히 무시하지 않고 ValueError로 거부한다 (두 라이브러리 모두 기본은 무시).
"""
import sys

# 긴급 정지 예외 클래스들. 백엔드를 만들 때 등록한다.
_FAILSAFE_ERRORS: list[type] = []

BACKENDS = ("pyautogui", "directinput")


def is_failsafe(err: BaseException) -> bool:
    """마우스를 화면 모서리로 옮겨서 난 긴급 정지인지. 어떤 백엔드든 같은 방식으로 판단한다."""
    return isinstance(err, tuple(_FAILSAFE_ERRORS))


def _register_failsafe(exc: type) -> None:
    if exc not in _FAILSAFE_ERRORS:
        _FAILSAFE_ERRORS.append(exc)


class InputBackend:
    """입력 백엔드 인터페이스. 좌표는 모두 실제 화면(가상 데스크톱) 픽셀 좌표다."""
    name = "base"

    def position(self) -> tuple[int, int]: raise NotImplementedError
    def move_to(self, x: int, y: int, duration: float = 0.0) -> None: raise NotImplementedError
    def move_rel(self, dx: int, dy: int) -> None: raise NotImplementedError
    def mouse_down(self, button: str = "left") -> None: raise NotImplementedError
    def mouse_up(self, button: str = "left") -> None: raise NotImplementedError
    def click(self, button: str = "left", clicks: int = 1, interval: float = 0.08) -> None:
        """현재 커서 위치에서 클릭한다."""
        raise NotImplementedError
    def scroll(self, notches: int) -> None:
        """휠 notches칸. 양수는 위로."""
        raise NotImplementedError
    def key_down(self, key: str) -> None: raise NotImplementedError
    def key_up(self, key: str) -> None: raise NotImplementedError
    def hotkey(self, *keys: str) -> None: raise NotImplementedError
    def write(self, text: str, interval: float = 0.01) -> None:
        """ASCII 텍스트 입력. 비ASCII는 Executor가 클립보드 붙여넣기로 처리한다."""
        raise NotImplementedError
    def is_valid_key(self, key: str) -> bool: raise NotImplementedError

    def check_keys(self, keys) -> None:
        bad = [k for k in keys if not self.is_valid_key(k)]
        if bad:
            raise ValueError(f"입력 백엔드 '{self.name}'가 지원하지 않는 키입니다: {', '.join(bad)}")


class PyAutoGuiBackend(InputBackend):
    name = "pyautogui"

    def __init__(self, pause: float = 0.05):
        import pyautogui
        self._p = pyautogui
        pyautogui.FAILSAFE = True  # 마우스를 왼쪽 위 모서리로 옮기면 긴급 정지
        pyautogui.PAUSE = pause    # 호출 사이 기본 간격
        # Windows에서 pyautogui.scroll(1)은 휠 한 칸의 1/120만 움직인다
        self.wheel_unit = 120 if sys.platform == "win32" else 1
        _register_failsafe(pyautogui.FailSafeException)

    def position(self):
        x, y = self._p.position()
        return int(x), int(y)

    def move_to(self, x, y, duration=0.0):
        self._p.moveTo(x, y, duration=duration)

    def move_rel(self, dx, dy):
        self._p.moveRel(dx, dy)

    def mouse_down(self, button="left"):
        self._p.mouseDown(button=button)

    def mouse_up(self, button="left"):
        self._p.mouseUp(button=button)

    def click(self, button="left", clicks=1, interval=0.08):
        self._p.click(button=button, clicks=clicks, interval=interval)

    def scroll(self, notches):
        self._p.scroll(notches * self.wheel_unit)

    def key_down(self, key):
        self.check_keys([key])
        self._p.keyDown(key)

    def key_up(self, key):
        self._p.keyUp(key)

    def hotkey(self, *keys):
        self.check_keys(keys)
        self._p.hotkey(*keys)

    def write(self, text, interval=0.01):
        self._p.write(text, interval=interval)

    def is_valid_key(self, key):
        return self._p.isValidKey(key)


class DirectInputBackend(InputBackend):
    """게임용. 스캔 코드 기반이라 DirectX 게임에서도 입력이 들어간다.
    move_rel은 상대 이동 API를 써서 1인칭 게임의 시점 회전(마우스 룩)에 쓸 수 있다."""
    name = "directinput"

    def __init__(self, pause: float = 0.05):
        import pydirectinput  # pydirectinput-rgx 패키지 (Windows 전용)
        self._d = pydirectinput
        pydirectinput.FAILSAFE = True
        pydirectinput.PAUSE = pause
        _register_failsafe(pydirectinput.FailSafeException)

    def position(self):
        x, y = self._d.position()
        return int(x), int(y)

    def move_to(self, x, y, duration=0.0):
        self._d.moveTo(x, y, duration=duration)

    def move_rel(self, dx, dy):
        self._d.moveRel(dx, dy, relative=True)

    def mouse_down(self, button="left"):
        self._d.mouseDown(button=button)

    def mouse_up(self, button="left"):
        self._d.mouseUp(button=button)

    def click(self, button="left", clicks=1, interval=0.08):
        self._d.click(button=button, clicks=clicks, interval=interval)

    def scroll(self, notches):
        self._d.scroll(notches)  # 한 번에 휠 한 칸(WHEEL_DELTA)

    def key_down(self, key):
        self.check_keys([key])
        self._d.keyDown(key)

    def key_up(self, key):
        self._d.keyUp(key)

    def hotkey(self, *keys):
        self.check_keys(keys)
        self._d.hotkey(*keys)

    def write(self, text, interval=0.01):
        # 스캔 코드는 US QWERTY 기준이라 대문자·기호는 Shift를 자동으로 끼워 넣어야 한다
        bad = sorted({ch for ch in text if not self.is_valid_key(ch) and not self.is_valid_key(ch.lower())})
        if bad:
            raise ValueError(f"입력 백엔드 'directinput'로 입력할 수 없는 문자입니다: {''.join(bad)!r}")
        self._d.typewrite(text, interval=interval, auto_shift=True)

    def is_valid_key(self, key):
        return self._d.is_valid_key(key)


def create(name: str, pause: float = 0.05) -> InputBackend:
    if name == "pyautogui":
        return PyAutoGuiBackend(pause)
    if name == "directinput":
        return DirectInputBackend(pause)
    raise ValueError(f"알 수 없는 입력 백엔드: {name} (사용 가능: {', '.join(BACKENDS)})")
