"""특정 창(게임 등)만 캡처하고 조작하기 위한 창 찾기/포커스 (PC_AGENT_WINDOW).

게임 창과 프로그램(터미널) 창을 나란히 띄우면, 모니터 전체를 캡처할 경우 터미널까지 스크린샷에 들어가고
look_at이 가정하는 '조준점 = 스크린샷 중앙'도 틀어진다. 그래서 게임 창의 클라이언트 영역(제목 표시줄과
테두리 제외)만 캡처 영역으로 쓴다. 좌표 변환은 Screen이 이 영역 기준으로 처리하므로,
Claude는 게임 창 밖(터미널)을 클릭할 수 없다.

pick_window는 순수 함수라 Linux에서도 테스트한다. 나머지는 Windows 전용(ctypes)이다.
"""
import ctypes
import time
from dataclasses import dataclass

# 이 문자열이 제목에 들어간 창은 고르지 않는다 (명령줄에 게임 이름이 들어간 터미널 창 등)
EXCLUDE_TITLE_PARTS = ("main.py", "bench.py", "uv run")


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    rect: tuple[int, int, int, int]  # 클라이언트 영역 (left, top, width, height), 물리 픽셀

    @property
    def area(self) -> int:
        return self.rect[2] * self.rect[3]


def pick_window(windows: list[WindowInfo], query: str, exclude_hwnds=()) -> WindowInfo | None:
    """제목에 query가 들어간(대소문자 무시) 창 중 클라이언트 영역이 가장 큰 창.
    최소화된 창(크기 0)과 이 프로그램의 콘솔 창은 뺀다."""
    q = query.strip().lower()
    if not q:
        return None
    candidates = [
        w for w in windows
        if q in w.title.lower()
        and w.hwnd not in exclude_hwnds
        and w.rect[2] > 0 and w.rect[3] > 0
        and not any(part in w.title.lower() for part in EXCLUDE_TITLE_PARTS)
    ]
    return max(candidates, key=lambda w: w.area, default=None)


# ---------- Windows 전용 ----------
def _user32():
    return ctypes.windll.user32


def client_rect(hwnd: int) -> tuple[int, int, int, int]:
    """창의 클라이언트 영역을 화면 좌표 (left, top, width, height)로. DPI 인식이 켜져 있어야 물리 픽셀이다."""
    from ctypes import wintypes

    u = _user32()
    rc = wintypes.RECT()
    u.GetClientRect(hwnd, ctypes.byref(rc))
    pt = wintypes.POINT(0, 0)
    u.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, rc.right - rc.left, rc.bottom - rc.top


def list_windows() -> list[WindowInfo]:
    from ctypes import wintypes

    u = _user32()
    out: list[WindowInfo] = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _):
        if u.IsWindowVisible(hwnd) and not u.IsIconic(hwnd):
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                out.append(WindowInfo(int(hwnd), buf.value, client_rect(hwnd)))
        return True

    u.EnumWindows(proc(callback), 0)
    return out


def find_window(query: str) -> WindowInfo:
    own_console = ctypes.windll.kernel32.GetConsoleWindow()
    found = pick_window(list_windows(), query, exclude_hwnds={own_console} if own_console else ())
    if found is None:
        raise LookupError(f"제목에 '{query}'가 들어간 창을 찾지 못했습니다. 창이 최소화되어 있지 않은지 확인하세요.")
    return found


def foreground() -> int:
    return int(_user32().GetForegroundWindow() or 0)


def focus(hwnd: int) -> bool:
    """창을 앞으로 가져온다. Windows는 다른 프로세스가 포커스를 뺏는 것을 막으므로,
    Alt를 한 번 눌렀다 떼서 제한을 푼 뒤 SetForegroundWindow를 부른다."""
    u = _user32()
    if foreground() == hwnd:
        return True
    VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002
    u.keybd_event(VK_MENU, 0, 0, 0)
    u.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    u.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    return foreground() == hwnd


def open_screen(max_long_edge: int, monitor_index: int, query: str):
    """(Screen, WindowInfo | None). query가 있으면 그 창의 클라이언트 영역만 캡처하고 창을 앞으로 가져온다."""
    from perception.capture import Screen

    if not query:
        return Screen(max_long_edge, monitor_index), None
    win = find_window(query)
    focus(win.hwnd)
    return Screen(max_long_edge, monitor_index, region=win.rect), win
