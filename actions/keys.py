"""Claude가 보내는 키 이름(xdotool 스타일)을 pyautogui 키 이름으로 변환한다.

예: "Return" -> "enter", "ctrl+s" -> ["ctrl", "s"], "alt+Tab" -> ["alt", "tab"]
GUI 의존성이 없는 순수 모듈이라 단위 테스트가 쉽다.
"""

KEY_MAP = {
    "return": "enter", "enter": "enter", "kp_enter": "enter",
    "escape": "esc", "esc": "esc",
    "backspace": "backspace", "back_space": "backspace",
    "delete": "delete", "del": "delete",
    "tab": "tab", "space": "space",
    "page_up": "pageup", "prior": "pageup", "pageup": "pageup",
    "page_down": "pagedown", "next": "pagedown", "pagedown": "pagedown",
    "home": "home", "end": "end", "insert": "insert",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "ctrl": "ctrl", "control": "ctrl", "control_l": "ctrl", "control_r": "ctrlright",
    "shift": "shift", "shift_l": "shift", "shift_r": "shiftright",
    "alt": "alt", "alt_l": "alt", "alt_r": "altright",
    "super": "win", "super_l": "win", "win": "win", "meta": "win", "cmd": "win",
    "caps_lock": "capslock", "print": "printscreen", "menu": "apps",
    "minus": "-", "plus": "+", "equal": "=", "comma": ",", "period": ".",
    "slash": "/", "backslash": "\\", "semicolon": ";", "apostrophe": "'",
    "grave": "`", "bracketleft": "[", "bracketright": "]",
    "hangul": "hangul", "hanja": "hanja",
}


def normalize_key(name: str) -> str:
    k = name.strip()
    low = k.lower()
    if low in KEY_MAP:
        return KEY_MAP[low]
    if low.startswith("f") and low[1:].isdigit():  # F1~F24
        return low
    if low.startswith("kp_") and low[3:].isdigit():  # 숫자 키패드
        return "num" + low[3:]
    if len(k) == 1:
        return low
    return low  # 모르는 키는 소문자로 그대로 넘기고, pyautogui가 거부하면 에러로 보고됨


def parse_combo(text: str) -> list[str]:
    """"ctrl+shift+t" -> ["ctrl", "shift", "t"]. 단독 "+" 키도 처리한다."""
    text = text.strip()
    if text == "+":
        return ["+"]
    parts = [p for p in text.split("+") if p != ""]
    if text.endswith("++"):  # "ctrl++" 같은 경우
        parts.append("+")
    return [normalize_key(p) for p in parts]


def parse_modifiers(text: str | None) -> list[str]:
    """클릭/스크롤 시 누르고 있을 수정 키. None이면 빈 리스트."""
    if not text:
        return []
    return parse_combo(text)
