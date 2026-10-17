"""마인크래프트(Java) 인벤토리 계열 화면의 칸 위치 찾기. GUI 의존성이 없는 순수 모듈이다.

Claude가 스크린샷에서 작은 칸의 좌표를 눈으로 짐작하면 자주 어긋난다. 그런데 마인크래프트의 인벤토리,
제작대, 상자, 화로는 칸 배치가 고정되어 있고, 화면 크기와 GUI 배율만 알면 각 칸의 위치를 정확히 계산할 수 있다.

- 배치(GUI 픽셀): 바닐라 메뉴 코드의 칸 좌표 (칸 왼쪽 위, 칸 크기 16, 간격 18).
- 화면 배치: GUI 배율 s, 화면 폭 W(물리 픽셀) → 축소 폭 ceil(W/s), 창 왼쪽 = (축소 폭 - 창 폭) // 2.
  레시피 책이 열려 있으면 인벤토리/제작대 창이 오른쪽으로 밀린다.
- 판정: 칸 테두리는 왼쪽·위가 어두운 회색(55,55,55), 오른쪽·아래가 흰색이다. 아이템은 칸 안쪽 16×16에만
  그려지므로 테두리는 가려지지 않는다. 가능한 (화면 종류, 배율, 레시피 책) 조합마다 테두리 색이 맞는 비율을
  재서 가장 잘 맞는 것을 고른다. 리소스 팩으로 칸 색이 바뀌면 찾지 못할 수 있다.
"""
import math
from dataclasses import dataclass
from typing import Callable

SLOT = 16
DARK = (55, 55, 55)
LIGHT = (255, 255, 255)
TOLERANCE = 24
MIN_SCORE = 0.85


@dataclass(frozen=True)
class Slot:
    id: str      # 짧은 영문 번호 (스크린샷에 그려 넣는 표시)
    name: str    # 한국어 이름
    gx: int      # GUI 픽셀, 칸 왼쪽 위 (창 기준)
    gy: int


def _grid(prefix: str, name: str, x0: int, y0: int, rows: int, cols: int) -> list[Slot]:
    out = []
    for r in range(rows):
        for c in range(cols):
            n = r * cols + c + 1
            label = f"{name} {r + 1}행 {c + 1}열" if rows > 1 else f"{name} {c + 1}"
            out.append(Slot(f"{prefix}{n}", label, x0 + c * 18, y0 + r * 18))
    return out


def _player(inv_y: int, hotbar_y: int) -> list[Slot]:
    return _grid("I", "인벤", 8, inv_y, 3, 9) + _grid("H", "핫바", 8, hotbar_y, 1, 9)


@dataclass(frozen=True)
class Layout:
    key: str
    name: str
    width: int
    height: int
    slots: tuple[Slot, ...]
    recipe_book: bool = False  # 레시피 책을 열 수 있는 화면


ARMOR = ("머리", "몸", "다리", "발")

LAYOUTS = [
    Layout("inventory", "인벤토리", 176, 166, tuple(
        [Slot("R", "제작 결과", 154, 28)]
        + _grid("C", "제작", 98, 18, 2, 2)
        + [Slot(f"A{i + 1}", f"갑옷 {ARMOR[i]}", 8, 8 + i * 18) for i in range(4)]
        + [Slot("O", "왼손", 77, 62)]
        + _player(84, 142)), recipe_book=True),
    Layout("crafting", "제작대", 176, 166, tuple(
        [Slot("R", "제작 결과", 124, 35)] + _grid("C", "제작", 30, 17, 3, 3) + _player(84, 142)),
        recipe_book=True),
    Layout("furnace", "화로", 176, 166, tuple(
        [Slot("F1", "재료", 56, 17), Slot("F2", "연료", 56, 53), Slot("R", "결과", 116, 35)]
        + _player(84, 142))),
    Layout("chest", "상자", 176, 168, tuple(_grid("K", "상자", 8, 18, 3, 9) + _player(85, 143))),
    Layout("large_chest", "큰 상자", 176, 222, tuple(_grid("K", "상자", 8, 18, 6, 9) + _player(139, 197))),
]


@dataclass
class Detection:
    layout: Layout
    gui_scale: int
    recipe_book: bool
    score: float
    left: int   # 창 왼쪽 위 (물리 픽셀, 캡처 영역 기준)
    top: int

    def center(self, slot: Slot) -> tuple[int, int]:
        """칸 중앙의 물리 픽셀 좌표 (캡처 영역 기준)."""
        s = self.gui_scale
        return self.left + (slot.gx + SLOT // 2) * s, self.top + (slot.gy + SLOT // 2) * s

    def corner(self, slot: Slot) -> tuple[int, int]:
        s = self.gui_scale
        return self.left + slot.gx * s, self.top + slot.gy * s


def max_gui_scale(width: int, height: int) -> int:
    """GUI 크기 '자동'일 때의 배율 (마인크래프트 Window.calculateScale과 같은 규칙)."""
    i = 1
    while i < width and i < height and width // (i + 1) >= 320 and height // (i + 1) >= 240:
        i += 1
    return i


def placement(layout: Layout, width: int, height: int, scale: int, recipe_book: bool) -> tuple[int, int] | None:
    """창 왼쪽 위의 물리 픽셀 좌표. 이 배율에서 창이 화면에 안 들어가면 None."""
    sw, sh = math.ceil(width / scale), math.ceil(height / scale)
    if sw < layout.width or sh < layout.height:
        return None
    if recipe_book:
        if sw < 379:  # 화면이 좁으면 레시피 책이 창을 밀지 않고 덮는다
            return None
        gl = 177 + (sw - layout.width - 200) // 2
    else:
        gl = (sw - layout.width) // 2
    gt = (sh - layout.height) // 2
    return gl * scale, gt * scale


def _near(rgb, target) -> bool:
    return all(abs(int(a) - b) <= TOLERANCE for a, b in zip(rgb[:3], target))


def score(det: Detection, width: int, height: int, getpixel: Callable[[tuple[int, int]], tuple]) -> float:
    """칸 테두리 색이 맞는 비율. 칸마다 왼쪽·위(어두움), 오른쪽·아래(밝음) 테두리 가운데를 본다."""
    s = det.gui_scale
    half = s // 2
    hits = total = 0
    for slot in det.layout.slots:
        x0, y0 = det.corner(slot)
        mid_x, mid_y = x0 + 8 * s, y0 + 8 * s
        probes = [
            ((x0 - s + half, mid_y), DARK),            # 왼쪽 테두리
            ((mid_x, y0 - s + half), DARK),            # 위 테두리
            ((x0 + SLOT * s + half, mid_y), LIGHT),    # 오른쪽 테두리
            ((mid_x, y0 + SLOT * s + half), LIGHT),    # 아래 테두리
        ]
        for (px, py), target in probes:
            total += 1
            if 0 <= px < width and 0 <= py < height and _near(getpixel((px, py)), target):
                hits += 1
    return hits / total if total else 0.0


def detect(width: int, height: int, getpixel: Callable[[tuple[int, int]], tuple],
           min_score: float = MIN_SCORE) -> Detection | None:
    """캡처 영역(게임 화면) 크기와 픽셀 읽기 함수로, 열려 있는 화면 종류와 칸 위치를 찾는다."""
    best: Detection | None = None
    for scale in range(1, max_gui_scale(width, height) + 1):
        for layout in LAYOUTS:
            for book in ((False, True) if layout.recipe_book else (False,)):
                pos = placement(layout, width, height, scale, book)
                if pos is None:
                    continue
                det = Detection(layout, scale, book, 0.0, *pos)
                det.score = score(det, width, height, getpixel)
                # 같은 점수면 칸이 많은 배치(더 구체적인 화면)를 고른다
                if best is None or (det.score, len(layout.slots)) > (best.score, len(best.layout.slots)):
                    best = det
    if best is None or best.score < min_score:
        return None
    return best
