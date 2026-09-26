"""UI 요소 목록의 필터링과 텍스트 출력. GUI 의존성이 없는 순수 모듈이다.

UIA 트리 탐색(perception/uia.py)이 모은 요소를 Claude에게 보여줄 한 줄짜리 목록으로 바꾼다.
좌표는 항상 스크린샷 좌표로 변환해서 보여준다 (computer 도구와 같은 좌표계).
"""
from dataclasses import dataclass
from typing import Callable

# UIA ControlTypeName → 목록에 표시할 짧은 이름
KIND_LABELS = {
    "ButtonControl": "버튼",
    "SplitButtonControl": "분할버튼",
    "EditControl": "입력칸",
    "DocumentControl": "문서",
    "ComboBoxControl": "콤보상자",
    "CheckBoxControl": "체크상자",
    "RadioButtonControl": "라디오",
    "MenuItemControl": "메뉴항목",
    "TabItemControl": "탭",
    "ListItemControl": "목록항목",
    "TreeItemControl": "트리항목",
    "DataItemControl": "데이터항목",
    "HyperlinkControl": "링크",
    "SliderControl": "슬라이더",
    "SpinnerControl": "스피너",
    "TextControl": "텍스트",
}
# 이름이 없어도 목록에 넣을 종류 (이름 없는 입력칸도 클릭 대상이 될 수 있음)
KEEP_UNNAMED = {"EditControl", "DocumentControl", "ComboBoxControl"}


@dataclass
class UIElement:
    kind: str                            # UIA ControlTypeName (예: "ButtonControl")
    name: str
    rect: tuple[int, int, int, int]      # 실제 화면 좌표 (left, top, right, bottom)
    enabled: bool = True
    value: str | None = None
    ref: object = None                   # 원본 UIA 컨트롤 (click_element에서 위치 재확인용)

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.rect
        return (left + right) // 2, (top + bottom) // 2


def is_listable(el: UIElement) -> bool:
    if el.kind not in KIND_LABELS:
        return False
    left, top, right, bottom = el.rect
    if right - left <= 1 or bottom - top <= 1:
        return False
    return bool(el.name.strip()) or el.kind in KEEP_UNNAMED


def filter_elements(elements: list[UIElement], query: str | None = None,
                    in_view: Callable[[int, int], bool] | None = None) -> list[UIElement]:
    """목록에 보여줄 요소만 남긴다. 같은 종류·이름·위치의 중복은 하나만 남긴다."""
    q = (query or "").strip().lower()
    seen = set()
    out = []
    for el in elements:
        if not is_listable(el):
            continue
        if q and q not in el.name.lower() and q not in (el.value or "").lower():
            continue
        if in_view is not None and not in_view(*el.center):
            continue
        key = (el.kind, el.name, el.rect)
        if key in seen:
            continue
        seen.add(key)
        out.append(el)
    return out


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_elements(elements: list[UIElement], to_shot: Callable[[int, int], tuple[int, int]],
                    window_title: str = "", total: int | None = None) -> str:
    """[id] 종류 "이름" 값="..." (x,y) 형식의 목록. id는 1부터 매긴다."""
    lines = [f'활성 창: "{_clip(window_title, 80)}"' if window_title else "활성 창: (알 수 없음)"]
    if not elements:
        lines.append("표시할 UI 요소가 없습니다.")
        return "\n".join(lines)
    for i, el in enumerate(elements, 1):
        x, y = to_shot(*el.center)
        parts = [f"[{i}]", KIND_LABELS.get(el.kind, el.kind)]
        if el.name.strip():
            parts.append(f'"{_clip(el.name, 60)}"')
        if el.value:
            parts.append(f'값="{_clip(el.value, 40)}"')
        if not el.enabled:
            parts.append("(비활성)")
        parts.append(f"({x},{y})")
        lines.append(" ".join(parts))
    if total is not None and total > len(elements):
        lines.append(f"... 외 {total - len(elements)}개 생략 (query로 좁혀서 다시 조회하세요)")
    return "\n".join(lines)
