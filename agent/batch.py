"""SDK 엔진용 행동 배치 실행 (순수 로직, claude_agent_sdk를 import하지 않음).

API 엔진에서는 computer 툴셋이 한 응답에 여러 tool_use를 보내고 하네스가 순서대로 실행했다.
SDK 엔진에서는 computer 툴셋을 쓸 수 없으므로, `computer` custom 도구 하나가 행동 배열을 받아
같은 규칙으로 실행한다.
- 순서대로 실행하고, 첫 실패 이후 행동은 실행하지 않는다 (뒤 동작은 앞 동작의 성공을 전제로 하므로)
- 배치가 관찰 행동으로 끝나지 않았으면 현재 화면을 결과 끝에 붙인다
- 결과는 MCP content 형식 ({"type": "image", "data", "mimeType"})으로 돌려준다
"""
from dataclasses import dataclass, field

from actions import backends

# computer_toolset_20260801의 17개 멤버와 같은 이름 + 게임용 look (Executor.do_<이름>으로 실행)
ACTIONS = (
    "screenshot", "zoom", "cursor_position",
    "left_click", "right_click", "middle_click", "double_click", "triple_click",
    "left_click_drag", "mouse_move", "left_mouse_down", "left_mouse_up", "scroll",
    "type", "key", "hold_key", "wait",
    "look",  # 툴셋에는 없는 추가 행동: 마우스 상대 이동 (커서가 고정된 게임의 시점 돌리기)
    "watch", "hold_until",  # 추가 행동: 연속 장면 보기, 내 PC에서 감시하며 키 누르기
)
OBSERVE_ACTIONS = {"screenshot", "zoom"}
MAX_ACTIONS = 20

_POINT = {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2}

COMPUTER_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_ACTIONS,
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(ACTIONS)},
                    "coordinate": _POINT,
                    "start_coordinate": _POINT,
                    "text": {"type": "string"},
                    "scroll_direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                    "scroll_amount": {"type": "integer", "minimum": 1},
                    "duration": {"type": "number", "minimum": 0},
                    "repeat": {"type": "integer", "minimum": 1},
                    "region": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                    "delta": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                    "frames": {"type": "integer", "minimum": 2, "maximum": 6},
                    "interval": {"type": "number", "minimum": 0.2, "maximum": 2},
                    "until": {"type": "string", "enum": ["change", "still"]},
                    "max_duration": {"type": "number", "minimum": 0.5, "maximum": 30},
                    "threshold": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["actions"],
    "additionalProperties": False,
}

COMPUTER_TOOL_DESCRIPTION = """\
Windows PC의 마우스와 키보드를 조작합니다. actions 배열의 행동을 순서대로 실행하고,
하나가 실패하면 나머지는 실행하지 않습니다. 배치가 screenshot/zoom으로 끝나지 않으면
실행 후 현재 화면 스크린샷이 결과 끝에 자동으로 붙습니다.
모든 좌표는 가장 최근 스크린샷의 픽셀 좌표 [x, y]입니다.

행동 (action: 필요한 필드):
- screenshot: 현재 화면
- zoom: region [x0, y0, x1, y1] 영역을 원본 해상도로 확대해서 봅니다 (좌표 기준은 바뀌지 않음)
- cursor_position: 현재 마우스 위치
- left_click / right_click / middle_click / double_click / triple_click: coordinate (생략하면 현재 위치).
  text에 "shift", "ctrl+shift" 같은 보조 키를 넣으면 누른 채 클릭
- left_click_drag: start_coordinate에서 coordinate까지 드래그 (text: 보조 키)
- mouse_move: coordinate
- left_mouse_down / left_mouse_up: 현재 위치에서 누르기/떼기
- scroll: scroll_direction (up/down/left/right), scroll_amount (기본 3), coordinate (선택), text (보조 키)
- type: text를 입력 (한글 가능)
- key: text에 xdotool 형식 키 조합 ("Return", "ctrl+s", "alt+F4", "super"), repeat (선택)
- hold_key: text 키를 duration초 동안 누르고 있기
- wait: duration초 기다리기
- look: delta [dx, dy]만큼 마우스를 '상대적으로' 움직입니다 (오른쪽·아래가 +). 마우스 커서가 사라지고
  화면에 고정되는 게임(마인크래프트 등)에서 시점을 돌릴 때 씁니다. mouse_move는 이런 게임에서 시점이 돌지 않습니다.
  마인크래프트 기본 감도(100%)에서는 delta 600 ≈ 90도, 1200 ≈ 180도입니다 (위아래도 같은 비율).
  감도가 다른 게임은 한 번 돌려 보고 결과(F3 Facing 등)를 보며 맞추세요.
  결과에 "주의: 시점이 돌지 않았을 가능성"이 나오면 게임이 마우스를 잡고 있지 않은 것이니 게임 화면부터 되돌리세요.
- watch: interval초(기본 0.5) 간격으로 frames장(기본 4, 최대 6)을 작게 찍어 한 번에 봅니다. 움직이는 화면에서
  무엇이 어느 방향으로 움직이는지 볼 때 씁니다 (몹이 다가오는지, 떨어지는 중인지 등). 이 작은 장면의 좌표는 클릭에 쓰지 마세요.
- hold_until: text 키(생략 가능)를 누른 채, 내 PC가 interval초(기본 0.5)마다 화면을 비교하다가 조건이 되면 스스로 멈춥니다.
  until="still": 화면이 멈추면 (예: 걷다가 벽에 막힘, 로딩 끝) / until="change": 처음 화면에서 크게 바뀌면 (예: 무언가 나타남).
  max_duration초(기본 5, 최대 30)가 지나면 멈춥니다. threshold로 민감도를 바꿀 수 있습니다 (still 기본 0.01, change 기본 0.03).
  예: {"action": "hold_until", "text": "w", "until": "still", "max_duration": 10} = 막힐 때까지 앞으로 걷기

예: {"actions": [{"action": "left_click", "coordinate": [640, 360]}, {"action": "type", "text": "안녕"}, {"action": "key", "text": "Return"}]}"""

NOT_EXECUTED = "실행 안 함: 앞의 행동이 실패했습니다."


@dataclass
class BatchResult:
    content: list[dict] = field(default_factory=list)  # MCP content 블록
    executed: int = 0
    errors: int = 0

    @property
    def is_error(self) -> bool:
        return self.errors > 0


def to_mcp_content(result) -> list[dict]:
    """Executor 반환값(str 또는 Messages API 형식 블록 목록)을 MCP content 블록으로 바꾼다."""
    if isinstance(result, str):
        return [{"type": "text", "text": result}]
    out = []
    for block in result:
        if block.get("type") == "image" and "source" in block:
            src = block["source"]
            out.append({"type": "image", "data": src["data"], "mimeType": src["media_type"]})
        else:
            out.append(block)
    return out


def _describe(action: dict) -> str:
    args = ", ".join(f"{k}={v!r}" for k, v in action.items() if k != "action")
    return f"{action.get('action')}({args})"


def run_batch(actions: list[dict], executor, recorder, auto_screenshot: bool = True) -> BatchResult:
    """행동 목록을 순서대로 실행한다. 긴급 정지 예외는 그대로 올린다."""
    out = BatchResult()
    failed = False
    last = None
    for i, action in enumerate(actions, 1):
        name = action.get("action")
        inp = {k: v for k, v in action.items() if k != "action"}
        label = f"[{i}] {_describe(action)}"
        if failed:
            out.content.append({"type": "text", "text": f"{label}: {NOT_EXECUTED}"})
            continue
        print(f"  → {name} {inp}")
        try:
            if name not in ACTIONS:
                raise NotImplementedError(f"알 수 없는 행동입니다: {name}")
            result = executor.run(name, inp)
            recorder.event("action", name=name, input=inp, ok=True)
        except Exception as err:
            if backends.is_failsafe(err):
                raise
            failed = True
            out.executed += 1
            out.errors += 1
            print(f"  ✗ {err}")
            recorder.event("action", name=name, input=inp, ok=False, error=str(err))
            out.content.append({"type": "text", "text": f"{label}: 오류: {err}"})
            continue
        out.executed += 1
        last = name
        blocks = to_mcp_content(result)
        if blocks and blocks[0].get("type") == "text":
            blocks[0] = {"type": "text", "text": f"{label}: {blocks[0]['text']}"}
        else:
            blocks.insert(0, {"type": "text", "text": f"{label}:"})
        out.content.extend(blocks)

    if auto_screenshot and not failed and last is not None and last not in OBSERVE_ACTIONS:
        out.content.append({"type": "text", "text": "실행 후 화면:"})
        out.content.extend(to_mcp_content([executor.screenshot_block("auto")]))
    return out
