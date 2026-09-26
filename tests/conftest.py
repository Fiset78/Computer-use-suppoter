"""GUI 모듈이 없는 환경(Linux/CI)에서도 루프 로직을 테스트할 수 있도록 pyautogui를 가짜로 바꾼다."""
import sys
import types

if "pyautogui" not in sys.modules:
    fake = types.ModuleType("pyautogui")

    class FailSafeException(Exception):
        pass

    fake.FailSafeException = FailSafeException
    fake.FAILSAFE = True
    fake.PAUSE = 0
    fake.calls = []

    def _record(name):
        return lambda *a, **k: fake.calls.append((name, a, k))

    for _name in ("click", "moveTo", "moveRel", "mouseDown", "mouseUp", "scroll", "write",
                  "hotkey", "keyDown", "keyUp"):
        setattr(fake, _name, _record(_name))
    fake.position = lambda: (0, 0)
    # 실제 pyautogui.KEY_NAMES의 일부. 테스트에서 '모르는 키' 처리를 확인하는 데 쓴다.
    fake.KEY_NAMES = {"enter", "esc", "ctrl", "shift", "alt", "win", "tab", "delete", "f4", "v", "a", "s", "+"}
    fake.isValidKey = lambda key: key in fake.KEY_NAMES
    sys.modules["pyautogui"] = fake
