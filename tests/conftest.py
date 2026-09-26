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

    for _name in ("click", "moveTo", "mouseDown", "mouseUp", "scroll", "write", "hotkey", "keyDown", "keyUp"):
        setattr(fake, _name, _record(_name))
    fake.position = lambda: (0, 0)
    sys.modules["pyautogui"] = fake
