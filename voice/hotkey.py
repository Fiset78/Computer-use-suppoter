"""전역 단축키. 어느 창에 있든 눌리면 콜백을 부른다.

Windows의 RegisterHotKey API를 ctypes로 직접 쓴다 (추가 라이브러리 없음).
단축키 문자열 해석(parse_hotkey)은 순수 함수라 어디서나 테스트할 수 있다.
"""
import ctypes
import sys
import threading

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT,
         "win": MOD_WIN, "super": MOD_WIN}
_KEYS = {"space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "pause": 0x13,
         "insert": 0x2D, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
         "`": 0xC0, "-": 0xBD, "=": 0xBB, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF}
_KEYS.update({f"f{i}": 0x6F + i for i in range(1, 25)})


def parse_hotkey(text: str) -> tuple[int, int]:
    """"ctrl+alt+space" → (보조 키 플래그, 가상 키 코드). 잘못되면 ValueError."""
    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    if not parts:
        raise ValueError("단축키가 비어 있습니다.")
    *mods, key = parts
    flags = 0
    for m in mods:
        if m not in _MODS:
            raise ValueError(f"알 수 없는 보조 키: {m} (사용 가능: ctrl, alt, shift, win)")
        flags |= _MODS[m]
    if not flags:
        raise ValueError("다른 프로그램의 입력을 가로채지 않도록 ctrl/alt/shift/win 중 하나 이상을 함께 써야 합니다.")
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key in _KEYS:
        vk = _KEYS[key]
    else:
        raise ValueError(f"알 수 없는 키: {key}")
    return flags | MOD_NOREPEAT, vk


class GlobalHotkey:
    """start()로 등록하고 stop()으로 해제한다. 콜백은 단축키를 감시하는 스레드에서 불린다."""

    def __init__(self, text: str, callback):
        self.text = text
        self.mods, self.vk = parse_hotkey(text)
        self.callback = callback
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()
        self.error: str | None = None

    def start(self) -> bool:
        """등록에 성공하면 True. 실패 이유는 self.error에 남는다."""
        if sys.platform != "win32":
            self.error = "전역 단축키는 Windows에서만 쓸 수 있습니다."
            return False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._ready.wait(2)
        return self.error is None

    def _loop(self) -> None:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        # RegisterHotKey는 메시지를 받을 스레드에서 호출해야 한다 (hWnd=None → 이 스레드의 메시지 큐)
        if not user32.RegisterHotKey(None, 1, self.mods, self.vk):
            self.error = f"단축키 {self.text}를 등록하지 못했습니다. 다른 프로그램이 이미 쓰고 있을 수 있습니다."
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        self.callback()
                    except Exception:
                        pass
        finally:
            user32.UnregisterHotKey(None, 1)

    def stop(self) -> None:
        if self._thread_id is not None and sys.platform == "win32":
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
