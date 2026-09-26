"""Windows UI Automation으로 활성 창의 UI 요소를 모은다 (Windows 전용).

- uiautomation 패키지를 쓴다. 이 모듈은 보조 도구 'uia'를 켤 때만 import 된다.
- DPI 인식이 켜진 프로세스에서는 BoundingRectangle이 mss와 같은 물리 픽셀 좌표로 나온다.
- 브라우저처럼 트리가 큰 창은 오래 걸리므로 깊이, 노드 수, 시간에 상한을 둔다.
"""
import ctypes
import time

import uiautomation as auto

from perception.elements import KIND_LABELS, UIElement

VALUE_KINDS = {"EditControl", "ComboBoxControl", "DocumentControl"}


def foreground_window():
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    return auto.ControlFromHandle(hwnd) if hwnd else None


def _read_value(control) -> str | None:
    try:
        pattern = control.GetValuePattern()
        return pattern.Value if pattern else None
    except Exception:
        return None


def _to_element(control) -> UIElement | None:
    try:
        kind = control.ControlTypeName
        r = control.BoundingRectangle
        el = UIElement(
            kind=kind,
            name=control.Name or "",
            rect=(r.left, r.top, r.right, r.bottom),
            enabled=bool(control.IsEnabled),
            ref=control,
        )
    except Exception:
        return None
    if kind in VALUE_KINDS:
        el.value = _read_value(control)
    return el


def collect(root, max_depth: int = 30, max_nodes: int = 3000, time_budget: float = 3.0) -> list[UIElement]:
    """root 아래 요소를 트리 순서(위→아래, 왼쪽→오른쪽 대체로)로 모은다.
    화면 밖이거나 크기가 0인 요소의 하위 트리는 건너뛴다."""
    deadline = time.perf_counter() + time_budget
    out: list[UIElement] = []
    visited = 0
    stack = [(root, 0)]
    while stack:
        control, depth = stack.pop()
        visited += 1
        if visited > max_nodes or time.perf_counter() > deadline:
            break
        try:
            if control is not root and control.IsOffscreen:
                continue
        except Exception:
            continue
        if control is not root:
            el = _to_element(control)
            if el is None:
                continue
            if el.kind in KIND_LABELS:
                out.append(el)
        if depth >= max_depth:
            continue
        # 형제를 순서대로 방문하도록 역순으로 스택에 넣는다
        children = []
        try:
            child = control.GetFirstChildControl()
            while child is not None:
                children.append(child)
                child = child.GetNextSiblingControl()
        except Exception:
            pass
        stack.extend((c, depth + 1) for c in reversed(children))
    return out


def current_rect(el: UIElement) -> tuple[int, int, int, int] | None:
    """클릭 직전에 요소 위치를 다시 읽는다. 사라졌거나 화면 밖이면 None."""
    control = el.ref
    if control is None:
        return el.rect
    try:
        if control.IsOffscreen:
            return None
        r = control.BoundingRectangle
    except Exception:
        return None
    if r.right - r.left <= 1 or r.bottom - r.top <= 1:
        return None
    return r.left, r.top, r.right, r.bottom
