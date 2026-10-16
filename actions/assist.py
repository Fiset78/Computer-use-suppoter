"""보조 도구 (로드맵 5단계). computer 툴셋과 함께 선언하는 custom 도구들이다.

- uia:  list_ui_elements, click_element  — Windows UI Automation 요소 목록과 요소 클릭
- wait: wait_for_change                  — 화면이 바뀌고 멈출 때까지 기다리기
- game: look, look_at, hold, move_item   — 1인칭 게임의 시점 회전, 동시·지속 입력, 인벤토리 아이템 옮기기

custom 도구의 tool_use에는 toolset_name이 없고, tool_result에도 넣지 않는다.
기준 성능과 비교할 수 있도록 config.ASSIST(환경 변수 PC_AGENT_ASSIST)로 켜고 끈다.
"""
import time

from actions import camera
from actions.keys import normalize_key
from perception import diff
from safety import killswitch
from perception.elements import UIElement, filter_elements, format_elements

MAX_LISTED = 150
MAX_HOLD_SECONDS = 10.0
HOLD_SLICE = 0.03  # hold 중 시점 회전을 나눠 보내는 간격(초)
MOUSE_BUTTONS = ("left", "right", "middle")
ITEM_PAUSE = 0.15  # move_item 클릭 사이 간격(초). 게임이 커서에 든 아이템을 갱신할 시간
# move_item 방식별 클릭 순서: (출발/도착, 버튼). 마인크래프트식 "클릭해서 집고, 클릭해서 놓기" 인벤토리
MOVE_MODES = {
    "all": [("from", "left"), ("to", "left")],                       # 묶음 전부
    "half": [("from", "right"), ("to", "left")],                     # 절반 집어서 전부 놓기
    "one": [("from", "left"), ("to", "right"), ("from", "left")],    # 한 개만 놓고 나머지는 되돌리기
}
_POINT = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}

_ANGLE_PROPS = {
    "yaw": {"type": "number", "description": "수평 회전(도). 양수 = 오른쪽, 음수 = 왼쪽. -180~180."},
    "pitch": {"type": "number", "description": "수직 회전(도). 양수 = 위, 음수 = 아래. -90~90."},
}

TOOL_DEFS = {
    "list_ui_elements": {
        "name": "list_ui_elements",
        "description": (
            "현재 활성 창의 UI 요소(버튼, 입력칸, 메뉴, 목록 항목, 텍스트 등)를 Windows UI Automation으로 "
            "읽어서 목록으로 돌려줍니다. 각 줄은 [id] 종류 \"이름\" 값=\"...\" (x,y) 형식이고, "
            "(x,y)는 스크린샷 좌표상의 요소 중심입니다. 작은 버튼이나 라벨을 정확히 찾거나, "
            "입력칸에 실제로 들어간 값을 확인할 때 스크린샷보다 확실합니다. "
            "id는 click_element에 쓰며, 다음 list_ui_elements 호출 전까지만 유효합니다. "
            "게임이나 일부 앱처럼 요소를 노출하지 않는 화면에서는 목록이 비어 있을 수 있습니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "이름이나 값에 이 문자열이 들어간 요소만 보기 (대소문자 무시). 생략하면 전체.",
                },
            },
            "additionalProperties": False,
        },
    },
    "click_element": {
        "name": "click_element",
        "description": (
            "list_ui_elements로 받은 id의 요소 중심을 클릭합니다. 클릭 직전에 요소 위치를 다시 읽으므로 "
            "창이 움직였어도 정확합니다. 요소가 사라졌으면 오류를 돌려주니 list_ui_elements를 다시 호출하세요."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "element_id": {"type": "integer", "description": "list_ui_elements 목록의 [id]"},
                "click": {
                    "type": "string",
                    "enum": ["left", "double", "right"],
                    "description": "클릭 종류 (기본 left)",
                },
            },
            "required": ["element_id"],
            "additionalProperties": False,
        },
    },
    "wait_for_change": {
        "name": "wait_for_change",
        "description": (
            "마지막으로 받은 스크린샷과 비교해 화면이 바뀔 때까지 기다리고, 바뀐 뒤 화면이 멈추면 "
            "결과 설명과 새 스크린샷을 돌려줍니다. 프로그램 실행, 페이지 로딩, 대화상자 표시처럼 "
            "시간이 걸리는 동작 뒤에 wait 대신 쓰세요. 이미 바뀌었으면 안정될 때까지만 기다립니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "timeout": {"type": "number", "description": "최대 대기 시간(초). 기본 5, 최대 30."},
                "region": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 4,
                    "maxItems": 4,
                    "description": "[x0, y0, x1, y1] 스크린샷 좌표. 이 영역의 변화만 봅니다. 생략하면 화면 전체.",
                },
            },
            "additionalProperties": False,
        },
    },
    "look": {
        "name": "look",
        "description": (
            "1인칭 게임에서 시점(카메라)을 각도만큼 돌립니다. 마우스 커서가 아니라 마우스 상대 이동을 보내므로, "
            "커서가 화면 중앙에 고정된 게임 화면에서 씁니다. 인벤토리처럼 커서가 보이는 화면에서는 쓰지 마세요."
        ),
        "input_schema": {
            "type": "object",
            "properties": _ANGLE_PROPS,
            "additionalProperties": False,
        },
    },
    "look_at": {
        "name": "look_at",
        "description": (
            "스크린샷의 한 점이 화면 중앙(조준점)에 오도록 시점을 돌립니다. 블록이나 대상을 조준할 때 씁니다. "
            "시야각으로 계산한 근사치라 화면 가장자리를 가리키면 조금 어긋날 수 있으니, 정확히 조준해야 하면 "
            "결과 스크린샷을 보고 한 번 더 보정하세요."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "coordinate": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "[x, y] 스크린샷 좌표",
                },
            },
            "required": ["coordinate"],
            "additionalProperties": False,
        },
    },
    "hold": {
        "name": "hold",
        "description": (
            "여러 키와 마우스 버튼을 동시에 누른 채 duration초 동안 유지한 뒤 뗍니다. 게임에서 이동(w), "
            "달리기(w + ctrl), 점프하며 이동(w + space), 블록 캐기(마우스 left 누르기)처럼 누르고 있어야 하는 "
            "동작에 씁니다. look을 주면 누르고 있는 동안 그 각도만큼 시점을 고르게 돌립니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "누를 키 이름들 (예: [\"w\", \"ctrl\"], [\"shift\"], [\"space\"]).",
                },
                "mouse": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(MOUSE_BUTTONS)},
                    "description": "누를 마우스 버튼들 (예: [\"left\"]).",
                },
                "duration": {"type": "number", "description": f"누르고 있을 시간(초). 최대 {MAX_HOLD_SECONDS:g}."},
                "look": {
                    "type": "object",
                    "properties": _ANGLE_PROPS,
                    "additionalProperties": False,
                    "description": "누르고 있는 동안 돌릴 시점 각도 (생략하면 돌리지 않음).",
                },
            },
            "required": ["duration"],
            "additionalProperties": False,
        },
    },
    "move_item": {
        "name": "move_item",
        "description": (
            "인벤토리, 상자, 제작대처럼 '클릭해서 집고, 클릭해서 놓는' 게임 화면에서 아이템을 한 칸에서 다른 칸으로 "
            "옮깁니다. 드래그(left_click_drag)는 게임에서 아이템이 커서에 남거나 여러 칸에 나뉘므로 대신 이것을 쓰세요. "
            "mode: all = 묶음 전부, half = 절반, one = 한 개만 놓고 나머지는 원래 칸으로 되돌림 (제작 칸에 하나씩 놓을 때). "
            "놓을 칸에 다른 아이템이 있으면 서로 바뀌어 커서에 아이템이 남을 수 있으니 결과 스크린샷을 확인하세요."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from": {**_POINT, "description": "집을 칸의 [x, y] 스크린샷 좌표"},
                "to": {**_POINT, "description": "놓을 칸의 [x, y] 스크린샷 좌표"},
                "mode": {"type": "string", "enum": list(MOVE_MODES), "description": "기본 all"},
            },
            "required": ["from", "to"],
            "additionalProperties": False,
        },
    },
}

GROUP_TOOLS = {
    "uia": ["list_ui_elements", "click_element"],
    "wait": ["wait_for_change"],
    "game": ["look", "look_at", "hold", "move_item"],
}

# 화면을 바꾸지 않거나 스스로 스크린샷을 돌려주는 도구 (루프가 자동 스크린샷을 붙이지 않음)
OBSERVE_TOOLS = {"list_ui_elements", "wait_for_change"}

# 입력을 보내는 도구 (실행 전에 대상 창 포커스를 확인)
INPUT_TOOLS = {"click_element", "look", "look_at", "hold", "move_item"}

PROMPT_HINTS = {
    "uia": (
        "- list_ui_elements로 활성 창의 버튼, 입력칸 등의 이름과 좌표를 정확히 알 수 있습니다. "
        "표준 Windows 앱에서는 좌표를 눈으로 추정하기보다 목록을 확인하고 click_element로 클릭하세요. "
        "입력한 값이 제대로 들어갔는지 확인할 때도 쓸 수 있습니다."
    ),
    "wait": (
        "- 프로그램 실행이나 로딩처럼 시간이 걸리는 동작 뒤에는 wait 대신 wait_for_change를 쓰세요."
    ),
    "game": (
        "- 1인칭 게임 화면에서는 마우스 커서가 화면 중앙에 고정되어 있으므로 mouse_move로 시점을 돌릴 수 없습니다. "
        "화면의 대상을 조준하려면 look_at, 각도로 돌리려면 look을 쓰세요. 블록 클릭·캐기는 조준한 뒤 "
        "화면 중앙에서 일어납니다.\n"
        "- 이동, 달리기, 캐기처럼 누르고 있어야 하는 동작은 hold를 쓰세요 (예: keys=[\"w\"], duration=1.5). "
        "게임은 생각하는 동안에도 흘러가므로 한 번에 너무 오래 움직이지 말고 짧게 움직이며 확인하세요.\n"
        "- 인벤토리, 제작대, 메뉴처럼 커서가 보이는 화면에서는 일반 클릭을 쓰세요. 아이템을 옮길 때는 "
        "left_click_drag를 쓰지 말고 move_item을 쓰세요 (드래그하면 아이템이 커서에 남습니다). "
        "인벤토리와 상자 사이로 빠르게 옮기거나 제작 결과를 꺼낼 때는 shift를 누른 채 클릭하세요 "
        "(left_click의 text=\"shift\"). 옮긴 뒤에는 커서에 아이템이 남아 있지 않은지 스크린샷으로 확인하세요."
    ),
}


def backend_warning(groups: list[str], backend_name: str) -> str | None:
    """game 도구는 상대 이동을 쓰므로 pyautogui(절대 좌표 기반)와는 게임에서 제대로 동작하지 않는다."""
    if "game" in groups and backend_name == "pyautogui":
        return ("주의: game 보조 도구는 마우스 상대 이동으로 시점을 돌립니다. 게임에서는 "
                "PC_AGENT_INPUT=directinput과 함께 쓰세요.")
    return None


def _angles(inp: dict | None) -> tuple[float, float]:
    inp = inp or {}
    yaw = max(-180.0, min(180.0, float(inp.get("yaw", 0))))
    pitch = max(-90.0, min(90.0, float(inp.get("pitch", 0))))
    return yaw, pitch


class AssistTools:
    def __init__(self, executor, groups: list[str], game_fov: float = 70.0, counts_per_deg: float = 6.667):
        self.executor = executor
        self.screen = executor.screen
        self.groups = list(groups)
        self.game_fov = game_fov
        self.counts_per_deg = counts_per_deg
        self.names = [n for g in self.groups for n in GROUP_TOOLS[g]]
        self._elements: list[UIElement] = []
        if "uia" in self.groups:
            from perception import uia  # Windows 전용 의존성은 켤 때만 불러온다
            self._uia = uia

    def tool_defs(self) -> list[dict]:
        return [TOOL_DEFS[n] for n in self.names]

    def prompt_hints(self) -> str:
        return "\n".join(PROMPT_HINTS[g] for g in self.groups)

    def has(self, name: str) -> bool:
        return name in self.names

    def run(self, name: str, inp: dict):
        if not self.has(name):
            raise NotImplementedError(f"켜지지 않은 보조 도구입니다: {name}")
        killswitch.check()
        if name in INPUT_TOOLS:
            self.executor.ensure_focus()
        return getattr(self, f"do_{name}")(inp)

    # ---------- uia ----------
    def do_list_ui_elements(self, inp):
        window = self._uia.foreground_window()
        if window is None:
            return "활성 창을 찾지 못했습니다."
        started = time.perf_counter()
        raw = self._uia.collect(window)
        shown = filter_elements(
            raw, inp.get("query"),
            in_view=lambda x, y: self.screen.in_bounds(*self.screen.to_shot(x, y)),
        )
        total = len(shown)
        self._elements = shown[:MAX_LISTED]
        title = getattr(window, "Name", "") or ""
        if self.executor.recorder:
            self.executor.recorder.event("uia_list", window=title, raw=len(raw), shown=total,
                                         seconds=round(time.perf_counter() - started, 2))
        return format_elements(self._elements, self.screen.to_shot, title, total)

    def do_click_element(self, inp):
        idx = int(inp["element_id"])
        if not 1 <= idx <= len(self._elements):
            raise ValueError(f"element_id {idx}가 없습니다. list_ui_elements를 다시 호출하세요.")
        el = self._elements[idx - 1]
        rect = self._uia.current_rect(el)
        if rect is None:
            raise LookupError(f"[{idx}] 요소가 사라졌거나 화면 밖입니다. list_ui_elements를 다시 호출하세요.")
        cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
        if not self.screen.in_bounds(*self.screen.to_shot(cx, cy)):
            raise ValueError(f"[{idx}] 요소가 캡처 중인 화면 밖에 있습니다.")
        click = inp.get("click", "left")
        button = "right" if click == "right" else "left"
        clicks = 2 if click == "double" else 1
        self.executor.input.move_to(cx, cy)
        self.executor.input.click(button=button, clicks=clicks, interval=0.08)
        time.sleep(self.executor.action_delay)
        x, y = self.screen.to_shot(cx, cy)
        return f'OK: [{idx}] "{el.name}" 클릭 ({x},{y})'

    # ---------- wait ----------
    def do_wait_for_change(self, inp):
        timeout = max(0.0, min(float(inp.get("timeout", 5)), 30.0))
        region = inp.get("region")
        if region is not None:
            x0, y0, x1, y1 = region
            if not (0 <= x0 < x1 <= self.screen.shot_w and 0 <= y0 < y1 <= self.screen.shot_h):
                raise ValueError(f"잘못된 region: {region} (스크린샷 크기 "
                                 f"{self.screen.shot_w}x{self.screen.shot_h})")
        crop = (lambda img: img.crop(tuple(region))) if region else (lambda img: img)

        frames = []

        def grab():
            img = self.screen.capture()
            frames.append(img)
            del frames[:-1]  # 마지막 전체 화면만 보관
            return crop(img)

        baseline = self.executor.last_shot or self.screen.capture()
        result = diff.wait_for_change(grab, crop(baseline), timeout)
        return [
            {"type": "text", "text": result.describe()},
            self.executor.image_block(frames[-1], "wait"),
        ]

    # ---------- game ----------
    def _turn(self, yaw: float, pitch: float) -> tuple[int, int]:
        dx, dy = camera.angles_to_counts(yaw, pitch, self.counts_per_deg)
        for sx, sy in camera.chunk_moves(dx, dy):
            if sx or sy:
                self.executor.input.move_rel(sx, sy)
                killswitch.sleep(0.005)
        return dx, dy

    def do_look(self, inp):
        yaw, pitch = _angles(inp)
        dx, dy = self._turn(yaw, pitch)
        killswitch.sleep(self.executor.action_delay)
        return f"OK: 수평 {yaw:+.1f}°, 수직 {pitch:+.1f}° 회전 (마우스 {dx:+d},{dy:+d})"

    def do_look_at(self, inp):
        x, y = inp["coordinate"]
        if not self.screen.in_bounds(x, y):
            raise ValueError(f"좌표 {inp['coordinate']}가 화면 밖입니다 "
                             f"(스크린샷 크기 {self.screen.shot_w}x{self.screen.shot_h}).")
        yaw, pitch = camera.shot_to_angles(x, y, self.screen.shot_w, self.screen.shot_h, self.game_fov)
        dx, dy = self._turn(yaw, pitch)
        killswitch.sleep(self.executor.action_delay)
        return f"OK: ({x},{y})를 조준 — 수평 {yaw:+.1f}°, 수직 {pitch:+.1f}° 회전 (마우스 {dx:+d},{dy:+d})"

    def do_hold(self, inp):
        keys = [normalize_key(k) for k in inp.get("keys") or []]
        buttons = list(inp.get("mouse") or [])
        if not keys and not buttons:
            raise ValueError("keys나 mouse 중 하나는 있어야 합니다.")
        bad = [b for b in buttons if b not in MOUSE_BUTTONS]
        if bad:
            raise ValueError(f"알 수 없는 마우스 버튼: {', '.join(bad)} (사용 가능: {', '.join(MOUSE_BUTTONS)})")
        duration = max(0.05, min(float(inp["duration"]), MAX_HOLD_SECONDS))
        yaw, pitch = _angles(inp.get("look"))
        dx, dy = camera.angles_to_counts(yaw, pitch, self.counts_per_deg)

        inp_backend = self.executor.input
        inp_backend.check_keys(keys)  # 하나라도 모르는 키면 아무것도 누르기 전에 거부
        if keys:
            self.executor.guard.check_key(keys)

        slices = max(1, round(duration / HOLD_SLICE))
        moves = list(zip(camera.split_counts(dx, slices), camera.split_counts(dy, slices)))
        pressed: list[tuple[str, str]] = []
        try:
            for k in keys:
                inp_backend.key_down(k)
                pressed.append(("key", k))
            for b in buttons:
                inp_backend.mouse_down(b)
                pressed.append(("mouse", b))
            for sx, sy in moves:
                if sx or sy:
                    inp_backend.move_rel(sx, sy)
                killswitch.sleep(duration / slices)
        finally:
            for kind, name in reversed(pressed):
                if kind == "key":
                    inp_backend.key_up(name)
                else:
                    inp_backend.mouse_up(name)
        killswitch.sleep(self.executor.action_delay)
        held = "+".join(keys + [f"마우스 {b}" for b in buttons])
        turned = f", 수평 {yaw:+.1f}° 수직 {pitch:+.1f}° 회전" if (dx or dy) else ""
        return f"OK: {held} {duration:g}초 누름{turned}"

    def do_move_item(self, inp):
        mode = inp.get("mode", "all")
        if mode not in MOVE_MODES:
            raise ValueError(f"알 수 없는 mode: {mode} (사용 가능: {', '.join(MOVE_MODES)})")
        points = {"from": self.executor._point(inp["from"]), "to": self.executor._point(inp["to"])}
        for i, (where, button) in enumerate(MOVE_MODES[mode]):
            if i:
                killswitch.sleep(ITEM_PAUSE)
            self.executor.click_at(points[where], button)
        killswitch.sleep(self.executor.action_delay)
        label = {"all": "전부", "half": "절반", "one": "한 개"}[mode]
        fx, fy = inp["from"]
        tx, ty = inp["to"]
        return f"OK: ({fx},{fy}) → ({tx},{ty}) {label} 옮김 (클릭 {len(MOVE_MODES[mode])}번)"
