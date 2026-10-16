"""긴급 정지 단축키 (기본 F12).

게임은 마우스 커서를 화면 중앙에 붙잡아 두므로 '마우스를 모서리로' 긴급 정지가 동작하지 않는다.
그래서 전역 키 상태를 따로 감시한다 (Windows GetAsyncKeyState 폴링, 게임에 포커스가 있어도 동작).

- 단축키를 누르면 감시 스레드가 즉시 눌린 키/마우스 버튼을 전부 떼고(on_trigger) 정지 플래그를 세운다.
- 메인 스레드는 check()/sleep()에서 플래그를 보고 EmergencyStop을 던진다.
  EmergencyStop은 KeyboardInterrupt의 하위 클래스라 Ctrl+C와 같은 경로로 처리된다.
- API 응답을 기다리는 중이면 응답이 온 뒤 첫 행동 전에 멈춘다 (키는 이미 떼어진 상태).
"""
import sys
import threading

_stop = threading.Event()


class EmergencyStop(KeyboardInterrupt):
    """긴급 정지 단축키로 멈춤."""


def trigger() -> None:
    _stop.set()


def reset() -> None:
    _stop.clear()


def triggered() -> bool:
    return _stop.is_set()


def check() -> None:
    if _stop.is_set():
        raise EmergencyStop("긴급 정지 단축키")


def sleep(seconds: float) -> None:
    """time.sleep 대신 쓴다. 기다리는 도중에 긴급 정지가 걸리면 바로 EmergencyStop을 던진다."""
    if _stop.wait(max(0.0, seconds)):
        raise EmergencyStop("긴급 정지 단축키")


def vk_code(name: str) -> int:
    """키 이름 → Windows 가상 키 코드. 게임에서 거의 쓰지 않는 키만 허용한다."""
    k = name.strip().lower()
    if k.startswith("f") and k[1:].isdigit() and 1 <= int(k[1:]) <= 24:
        return 0x70 + int(k[1:]) - 1
    named = {"pause": 0x13, "scrolllock": 0x91, "scroll_lock": 0x91}
    if k in named:
        return named[k]
    raise ValueError(f"긴급 정지 키로 쓸 수 없는 키입니다: {name} (F1~F24, pause, scrolllock)")


class HotkeyWatcher:
    def __init__(self, key: str, on_trigger=None, interval: float = 0.03):
        self.key = key
        self.vk = vk_code(key)
        self.on_trigger = on_trigger
        self.interval = interval
        self._quit = threading.Event()
        self._thread = threading.Thread(target=self._run, name="killswitch", daemon=True)

    def _run(self) -> None:
        import ctypes
        get = ctypes.windll.user32.GetAsyncKeyState
        get(self.vk)  # 이전에 눌렸던 기록을 비운다
        while not self._quit.wait(self.interval):
            if get(self.vk) & 0x8000:
                trigger()
                if self.on_trigger is not None:
                    try:
                        self.on_trigger()
                    except Exception:
                        pass
                return

    def start(self) -> "HotkeyWatcher":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._quit.set()


def stop_hint(watcher: HotkeyWatcher | None) -> str:
    keys = [f"{watcher.key.upper()} 키"] if watcher else []
    return "긴급 정지: " + " / ".join(keys + ["마우스를 왼쪽 위 모서리로", "Ctrl+C"])


def start_hotkey(key: str, on_trigger=None) -> HotkeyWatcher | None:
    """Windows에서만 감시 스레드를 시작한다. 그 밖의 OS나 빈 key면 None."""
    reset()
    if not key or sys.platform != "win32":
        return None
    return HotkeyWatcher(key, on_trigger).start()
