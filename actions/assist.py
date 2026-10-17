"""보조 도구 (로드맵 5단계). computer 툴셋과 함께 선언하는 custom 도구들이다.

- uia:  list_ui_elements, click_element  — Windows UI Automation 요소 목록과 요소 클릭
- wait: wait_for_change                  — 화면이 바뀌고 멈출 때까지 기다리기

custom 도구의 tool_use에는 toolset_name이 없고, tool_result에도 넣지 않는다.
기준 성능과 비교할 수 있도록 config.ASSIST(환경 변수 PC_AGENT_ASSIST)로 켜고 끈다.
"""
import time

from perception import diff
from perception.elements import UIElement, filter_elements, format_elements

MAX_LISTED = 150

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
}

GROUP_TOOLS = {
    "uia": ["list_ui_elements", "click_element"],
    "wait": ["wait_for_change"],
}

# 화면을 바꾸지 않거나 스스로 스크린샷을 돌려주는 도구 (루프가 자동 스크린샷을 붙이지 않음)
OBSERVE_TOOLS = {"list_ui_elements", "wait_for_change"}

PROMPT_HINTS = {
    "uia": (
        "- list_ui_elements로 활성 창의 버튼, 입력칸 등의 이름과 좌표를 정확히 알 수 있습니다. "
        "표준 Windows 앱에서는 좌표를 눈으로 추정하기보다 목록을 확인하고 click_element로 클릭하세요. "
        "입력한 값이 제대로 들어갔는지 확인할 때도 쓸 수 있습니다."
    ),
    "wait": (
        "- 프로그램 실행이나 로딩처럼 시간이 걸리는 동작 뒤에는 wait 대신 wait_for_change를 쓰세요."
    ),
}


class AssistTools:
    def __init__(self, executor, groups: list[str]):
        self.executor = executor
        self.screen = executor.screen
        self.groups = list(groups)
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
