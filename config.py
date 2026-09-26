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

# 각 행동 후 UI가 반응할 때까지 기다리는 시간(초)
ACTION_DELAY = float(os.getenv("PC_AGENT_ACTION_DELAY", "0.4"))

# 배치가 스크린샷으로 끝나지 않으면 하네스가 자동으로 스크린샷을 붙여줄지 여부
AUTO_SCREENSHOT = True

# 실행 기록 저장 폴더
RUNS_DIR = os.getenv("PC_AGENT_RUNS_DIR", "runs")
