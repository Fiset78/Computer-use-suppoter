"""마인크래프트 칸 찾기: 합성한 화면에서 화면 종류·배율·레시피 책 위치를 맞히는지."""
import random

import pytest
from PIL import Image, ImageDraw

from perception import mc_slots
from perception.mc_slots import LAYOUTS, detect, max_gui_scale, placement


def render(layout_key, width=1520, height=1009, scale=None, book=False, items=True, seed=0):
    """칸 테두리를 바닐라와 같은 색으로 그린 가짜 게임 화면."""
    layout = next(l for l in LAYOUTS if l.key == layout_key)
    scale = scale or max_gui_scale(width, height)
    img = Image.new("RGB", (width, height), (40, 60, 40))  # 흐린 게임 배경
    left, top = placement(layout, width, height, scale, book)
    d = ImageDraw.Draw(img)
    d.rectangle([left, top, left + layout.width * scale - 1, top + layout.height * scale - 1], fill=(198, 198, 198))
    rnd = random.Random(seed)
    for slot in layout.slots:
        x0, y0 = left + (slot.gx - 1) * scale, top + (slot.gy - 1) * scale
        size = 18 * scale
        d.rectangle([x0, y0, x0 + size - 1, y0 + size - 1], fill=(255, 255, 255))           # 오른쪽·아래 흰색
        d.rectangle([x0, y0, x0 + size - 1 - scale, y0 + size - 1 - scale], fill=(55, 55, 55))  # 왼쪽·위 어두움
        ix, iy = x0 + scale, y0 + scale
        d.rectangle([ix, iy, ix + 16 * scale - 1, iy + 16 * scale - 1], fill=(139, 139, 139))
        if items and rnd.random() < 0.5:  # 아이템은 칸 안쪽에만 그려진다
            d.rectangle([ix + scale, iy + scale, ix + 15 * scale - 1, iy + 15 * scale - 1],
                        fill=tuple(rnd.randrange(256) for _ in range(3)))
    return img, layout, scale, (left, top)


def test_max_gui_scale_matches_minecraft_auto():
    assert max_gui_scale(1920, 1080) == 4
    assert max_gui_scale(1520, 1009) == 4
    assert max_gui_scale(1280, 720) == 3
    assert max_gui_scale(854, 480) == 2


@pytest.mark.parametrize("key", [l.key for l in LAYOUTS])
def test_detects_each_screen(key):
    img, layout, scale, (left, top) = render(key)
    det = detect(img.width, img.height, img.getpixel)
    assert det is not None and det.layout.key == key and det.gui_scale == scale
    assert (det.left, det.top) == (left, top) and det.score == 1.0
    assert not det.recipe_book


def test_detects_non_auto_scale_and_recipe_book():
    img, _, _, _ = render("crafting", scale=2, book=True)
    det = detect(img.width, img.height, img.getpixel)
    assert det.layout.key == "crafting" and det.gui_scale == 2 and det.recipe_book


def test_slot_centers_land_inside_slots():
    img, layout, scale, _ = render("inventory", items=False)
    det = detect(img.width, img.height, img.getpixel)
    for slot in layout.slots:
        assert img.getpixel(det.center(slot)) == (139, 139, 139)
    ids = [s.id for s in layout.slots]
    assert len(ids) == len(set(ids)) == 46
    assert {"R", "C1", "C4", "A1", "A4", "O", "I1", "I27", "H1", "H9"} <= set(ids)


def test_no_inventory_open_returns_none():
    img = Image.new("RGB", (1520, 1009), (120, 160, 220))
    assert detect(img.width, img.height, img.getpixel) is None


# ---------- find_slots / click_slot / move_item(칸 번호) ----------
from actions.assist import AssistTools  # noqa: E402
from actions.executor import Executor  # noqa: E402
from test_game import Guard  # noqa: E402
from test_game import GuiBackend  # noqa: E402


class SlotScreen:
    """1520x1009 게임 창을 왼쪽 위 (100, 50)에 두고, 1280 폭으로 줄여 보내는 가짜 Screen."""

    def __init__(self, img):
        self.img = img
        self.left, self.top = 100, 50
        self.scale = 1280 / img.width
        self.shot_w, self.shot_h = round(img.width * self.scale), round(img.height * self.scale)

    def capture_raw(self):
        return self.img

    def shrink(self, img):
        return img.resize((self.shot_w, self.shot_h))

    def in_bounds(self, x, y):
        return 0 <= x < self.shot_w and 0 <= y < self.shot_h

    def to_screen(self, x, y):
        return self.left + round(x / self.scale), self.top + round(y / self.scale)

    def to_shot(self, sx, sy):
        return round((sx - self.left) * self.scale), round((sy - self.top) * self.scale)


def make_tools(img):
    b = GuiBackend()
    b.click_hold = 0.0
    ex = Executor(SlotScreen(img), Guard(), None, action_delay=0, backend=b)
    return AssistTools(ex, ["game", "minecraft"]), ex, b


def clicks(b):
    pos, out, held = None, [], []
    for c in b.calls:
        if c[0] == "move_to":
            pos = (c[1], c[2])
        elif c[0] == "key_down":
            held.append(c[1])
        elif c[0] == "key_up":
            held.remove(c[1])
        elif c[0] == "click":
            out.append((pos, c[1], c[2], tuple(held)))
    return out


def test_find_slots_lists_numbers_and_labeled_image():
    img, layout, _, _ = render("crafting")
    assist, _, _ = make_tools(img)
    text, image = assist.run("find_slots", {})
    assert image["type"] == "image"
    t = text["text"]
    assert t.startswith("화면: 제작대 (GUI 배율 4")
    assert "R(" in t and "C9(" in t and "I27(" in t and "H9(" in t


def test_click_slot_hits_slot_center_with_shift():
    img, layout, _, _ = render("chest")
    assist, ex, b = make_tools(img)
    assist.run("find_slots", {})
    det = assist._slots
    assist.run("click_slot", {"slot": "k3", "click": "shift"})
    slot = next(s for s in layout.slots if s.id == "K3")
    cx, cy = det.center(slot)
    assert clicks(b) == [((100 + cx, 50 + cy), "left", 1, ("shift",))]


def test_move_item_by_slot_ids():
    img, layout, _, _ = render("inventory")
    assist, _, b = make_tools(img)
    assist.run("find_slots", {})
    out = assist.run("move_item", {"from_slot": "I1", "to_slot": "C1", "mode": "one"})
    det = assist._slots
    by_id = {s.id: det.center(s) for s in layout.slots}
    pts = [(p[0] - 100, p[1] - 50) for p, *_ in clicks(b)] if clicks(b) else []
    # GuiBackend.click_hold=0 → press()는 click()을 한 번 보낸다
    assert pts == [by_id["I1"], by_id["C1"], by_id["I1"]]
    assert out.startswith("OK: I1 → C1 한 개")


def test_slot_tools_refuse_when_screen_changed_or_unknown():
    img, _, _, _ = render("furnace")
    assist, ex, b = make_tools(img)
    with pytest.raises(LookupError):
        assist.run("click_slot", {"slot": "R"})  # find_slots 전
    assist.run("find_slots", {})
    with pytest.raises(ValueError):
        assist.run("click_slot", {"slot": "C1"})  # 화로에는 제작 칸이 없음
    ex.screen.img = Image.new("RGB", img.size, (120, 160, 220))  # 창을 닫음
    with pytest.raises(LookupError, match="다시"):
        assist.run("click_slot", {"slot": "R"})
    assert clicks(b) == []


def test_find_slots_when_nothing_open():
    assist, _, _ = make_tools(Image.new("RGB", (1520, 1009), (120, 160, 220)))
    assert "찾지 못했습니다" in assist.run("find_slots", {})
