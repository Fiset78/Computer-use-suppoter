"""전역 설정. 환경 변수로 덮어쓸 수 있다."""
import os

# 사용할 모델 (computer_toolset_20260801 지원 모델: Sonnet 5, Opus 5 / 5.5 등)
MODEL = os.getenv("PC_AGENT_MODEL", "claude-sonnet-5")

# 에이전트 루프 최대 반복 수 (무한 루프·비용 폭주 방지)
MAX_STEPS = int(os.getenv("PC_AGENT_MAX_STEPS", "30"))

# Claude에게 보내는 스크린샷의 긴 변 최대 길이(px).
# 공식 문서 권장: 일반 데스크톱 작업은 1280x720 수준.
MAX_LONG_EDGE = int(os.getenv("PC_AGENT_MAX_LONG_EDGE", "1280"))

# 캡처할 모니터 번호 (mss 기준: 1 = 주 모니터)
MONITOR_INDEX = int(os.getenv("PC_AGENT_MONITOR", "1"))

# 이 문자열이 제목에 들어간 창(예: "Minecraft")만 캡처하고, 행동 전에 그 창을 활성 창으로 만든다.
# 게임 창 옆에 프로그램(터미널) 창을 함께 띄워 둘 때 쓴다. 비우면 모니터 전체를 캡처한다.
WINDOW = os.getenv("PC_AGENT_WINDOW", "").strip()

# 각 행동 후 UI가 반응할 때까지 기다리는 시간(초)
ACTION_DELAY = float(os.getenv("PC_AGENT_ACTION_DELAY", "0.4"))

# 배치가 스크린샷으로 끝나지 않으면 하네스가 자동으로 스크린샷을 붙여줄지 여부
AUTO_SCREENSHOT = True

# 실행 기록 저장 폴더
RUNS_DIR = os.getenv("PC_AGENT_RUNS_DIR", "runs")


# 켤 보조 도구 묶음 (로드맵 5단계). 쉼표로 구분: uia, wait, game, all. 비우면 순수 computer use (기준 성능).
#   uia  = list_ui_elements + click_element (Windows UI Automation)
#   wait = wait_for_change (화면 변화 감지)
#   game = look + look_at + hold + move_item (1인칭 게임의 시점 회전, 동시·지속 입력, 아이템 옮기기.
#          directinput 백엔드와 함께 쓴다)
#   minecraft = find_slots + click_slot (마인크래프트 인벤토리 칸 위치를 계산해 번호로 알려줌)
ASSIST_GROUPS = ("uia", "wait", "game", "minecraft")


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

# 입력 백엔드 (로드맵 7단계): pyautogui (일반 앱, 기본) | directinput (게임, pydirectinput-rgx)
INPUT_BACKEND = os.getenv("PC_AGENT_INPUT", "pyautogui").strip().lower()


def _optional_float(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    return float(value) if value else None


# 클릭 타이밍(초). 비우면 백엔드 기본값 (pyautogui 0/0, directinput 0.05/0.05).
# 게임 인벤토리에서 클릭이 씹히면 늘린다.
CLICK_SETTLE = _optional_float("PC_AGENT_CLICK_SETTLE")  # 커서 이동 후 클릭까지
CLICK_HOLD = _optional_float("PC_AGENT_CLICK_HOLD")      # 누르고 뗄 때까지

# 긴급 정지 단축키 (F1~F24, pause, scrolllock). 게임은 커서를 붙잡아서 '마우스를 모서리로'가 안 되므로 필요하다.
# 빈 값이면 끈다.
KILL_KEY = os.getenv("PC_AGENT_KILL_KEY", "f12").strip().lower()

# game 보조 도구: 게임의 세로 시야각(도). 마인크래프트 기본 FOV는 70 ("FOV 효과"는 0%로 꺼 두는 것을 권장).
GAME_FOV = float(os.getenv("PC_AGENT_GAME_FOV", "70"))

# game 보조 도구: 시점 1도를 돌리는 데 필요한 마우스 상대 이동량(count).
# 마인크래프트 Java: 1 count당 회전 = 1.2 × (감도×0.6 + 0.2)³ 도.
# 기본 감도(화면 표시 100% = 내부값 0.5)면 0.15도/count → 6.667 count/도.
GAME_COUNTS_PER_DEG = float(os.getenv("PC_AGENT_GAME_COUNTS_PER_DEG", "6.667"))

# 지식 메모 파일 (예: memory/minecraft.md). 실행 시작 때 읽어 첫 메시지에 넣고, Claude가 remember/forget으로 고친다.
# 비우면 끈다 (기준 성능 측정은 끈 상태로).
MEMORY_FILE = os.getenv("PC_AGENT_MEMORY", "").strip()

# 작업이 끝난 뒤 한 번 더 물어 교훈을 정리하게 할지 (API 호출 1~2번 추가)
MEMORY_REFLECT = os.getenv("PC_AGENT_MEMORY_REFLECT", "1") != "0"

# 첫 메시지에 넣을 메모의 최대 글자 수 (넘으면 최근 메모부터)
MEMORY_MAX_CHARS = int(os.getenv("PC_AGENT_MEMORY_MAX_CHARS", "4000"))

# 참고 자료 파일 (쉼표로 구분). 첫 메시지에 넣는다. 텍스트, 이미지(png/jpg/gif/webp), PDF. 읽기 전용.
REFS = [t.strip() for t in os.getenv("PC_AGENT_REFS", "").split(",") if t.strip()]

# 참고 자료 텍스트를 모두 합친 최대 글자 수 (넘으면 뒷부분 생략)
REFS_MAX_CHARS = int(os.getenv("PC_AGENT_REFS_MAX_CHARS", "20000"))

# main.py 시작 메뉴가 보여줄 폴더: 지식 메모 파일(.md)과 참고 자료
MEMORY_DIR = os.getenv("PC_AGENT_MEMORY_DIR", "memory")
REFS_DIR = os.getenv("PC_AGENT_REFS_DIR", "refs")
