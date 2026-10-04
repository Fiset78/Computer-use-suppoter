"""전역 설정. 환경 변수로 덮어쓸 수 있다."""
import os

# 에이전트 엔진: sdk | api
#   sdk = Claude Agent SDK (Claude Code CLI + 구독 로그인, API 키 불필요). 기본값
#   api = Anthropic Messages API 직접 호출 (computer_toolset_20260801, ANTHROPIC_API_KEY 필요)
ENGINES = ("sdk", "api")
ENGINE = os.getenv("PC_AGENT_ENGINE", "sdk").strip().lower()

# 사용할 모델 (computer_toolset_20260801 지원 모델: Sonnet 5, Opus 5 / 5.5 등)
MODEL = os.getenv("PC_AGENT_MODEL", "claude-sonnet-5")

# 에이전트 루프 최대 반복 수 (무한 루프·비용 폭주 방지)
MAX_STEPS = int(os.getenv("PC_AGENT_MAX_STEPS", "30"))

# Claude에게 보내는 스크린샷의 긴 변 최대 길이(px).
# 공식 문서 권장: 일반 데스크톱 작업은 1280x720 수준.
MAX_LONG_EDGE = int(os.getenv("PC_AGENT_MAX_LONG_EDGE", "1280"))

# 캡처할 모니터 번호 (mss 기준: 1 = 주 모니터)
MONITOR_INDEX = int(os.getenv("PC_AGENT_MONITOR", "1"))

# 각 행동 후 UI가 반응할 때까지 기다리는 시간(초)
ACTION_DELAY = float(os.getenv("PC_AGENT_ACTION_DELAY", "0.4"))

# 배치가 스크린샷으로 끝나지 않으면 하네스가 자동으로 스크린샷을 붙여줄지 여부
AUTO_SCREENSHOT = True

# 실행 기록 저장 폴더
RUNS_DIR = os.getenv("PC_AGENT_RUNS_DIR", "runs")


# 켤 보조 도구 묶음 (로드맵 5단계). 쉼표로 구분: uia, wait, all. 비우면 순수 computer use (기준 성능).
#   uia  = list_ui_elements + click_element (Windows UI Automation)
#   wait = wait_for_change (화면 변화 감지)
ASSIST_GROUPS = ("uia", "wait")


def parse_assist(text: str | None) -> list[str]:
    """"uia,wait" -> ["uia", "wait"]. "all"은 전체, 빈 값/"none"은 없음."""
    items = [t.strip().lower() for t in (text or "").split(",") if t.strip()]
    if not items or items in (["none"], ["off"]):
        return []
    if "all" in items:
        return list(ASSIST_GROUPS)
    unknown = [t for t in items if t not in ASSIST_GROUPS]
    if unknown:
        raise ValueError(f"알 수 없는 보조 도구: {', '.join(unknown)} "
                         f"(사용 가능: {', '.join(ASSIST_GROUPS)}, all)")
    return [g for g in ASSIST_GROUPS if g in items]


ASSIST = parse_assist(os.getenv("PC_AGENT_ASSIST"))

# Claude Code 내장 웹 도구(WebSearch, WebFetch)를 켤지 여부. sdk 엔진 전용.
# 켜면 브라우저를 조작하지 않고 텍스트로 검색할 수 있다. 순수 화면 조작 성능을 잴 때는 끈다 (기본 꺼짐).
WEB = os.getenv("PC_AGENT_WEB", "0").strip().lower() in ("1", "true", "yes", "on")

# 컨텍스트 관리 전략 (로드맵 6단계): server | prune | none
#   server = 서버 측 tool result clearing (권장, 모든 모델에서 안전)
#   prune  = 클라이언트 측 스크린샷 가지치기 (Opus 5.5 / Fable 5.1에서는 자동으로 server로 바뀜)
#   none   = 아무것도 지우지 않음
CONTEXT = os.getenv("PC_AGENT_CONTEXT", "server").strip().lower()

# prompt caching 중단점 사용 여부 (비용 절감, 동작은 바뀌지 않음)
PROMPT_CACHE = os.getenv("PC_AGENT_PROMPT_CACHE", "1") != "0"

# server: 입력 토큰이 CLEAR_TRIGGER를 넘으면 최근 CLEAR_KEEP개 도구 호출 결과만 남기고 지운다.
# 한 번에 최소 CLEAR_AT_LEAST 토큰 이상 지울 수 있을 때만 지운다 (지울 때마다 캐시가 다시 써지므로).
CLEAR_TRIGGER = int(os.getenv("PC_AGENT_CLEAR_TRIGGER", "40000"))
CLEAR_KEEP = int(os.getenv("PC_AGENT_CLEAR_KEEP", "6"))
CLEAR_AT_LEAST = int(os.getenv("PC_AGENT_CLEAR_AT_LEAST", "10000"))

# prune: 스크린샷이 PRUNE_KEEP + PRUNE_BATCH장을 넘으면 최근 PRUNE_KEEP장만 남긴다.
PRUNE_KEEP = int(os.getenv("PC_AGENT_PRUNE_KEEP", "3"))
PRUNE_BATCH = int(os.getenv("PC_AGENT_PRUNE_BATCH", "10"))

# 실행 창의 음성 입력 전역 단축키. 누르면 말하기 시작/멈추기, 실행 중에 누르면 정지
HOTKEY = os.getenv("PC_AGENT_HOTKEY", "ctrl+alt+space")
# 직접 정하지 않았을 때, 기본 단축키를 다른 프로그램이 쓰고 있으면 차례로 시도할 단축키
HOTKEY_FALLBACKS = ("ctrl+alt+f9", "ctrl+shift+f9", "ctrl+alt+f12")
HOTKEY_FROM_ENV = bool(os.getenv("PC_AGENT_HOTKEY"))

# 입력 백엔드 (로드맵 7단계): pyautogui (일반 앱, 기본) | directinput (게임, pydirectinput-rgx)
INPUT_BACKEND = os.getenv("PC_AGENT_INPUT", "pyautogui").strip().lower()
