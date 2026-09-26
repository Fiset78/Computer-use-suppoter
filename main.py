"""진입점.

사용법:
    uv run main.py "메모장을 열고 '안녕하세요'라고 입력해줘"
    uv run main.py            # 실행 후 목표를 입력

긴급 정지: 마우스를 화면 왼쪽 위 모서리로 급히 옮기거나, 터미널에서 Ctrl+C
"""
import sys

# DPI 설정은 다른 GUI 모듈(pyautogui)을 import 하기 전에 해야 한다
from perception.capture import enable_dpi_awareness

enable_dpi_awareness()

import pyautogui  # noqa: E402

import config  # noqa: E402
from actions.executor import Executor  # noqa: E402
from agent import loop  # noqa: E402
from logs.recorder import Recorder  # noqa: E402
from perception.capture import Screen  # noqa: E402
from safety.guard import Guard  # noqa: E402


def main() -> None:
    goal = " ".join(sys.argv[1:]).strip() or input("목표를 입력하세요: ").strip()
    if not goal:
        print("목표가 비어 있습니다.")
        return

    screen = Screen(config.MAX_LONG_EDGE, config.MONITOR_INDEX)
    print(f"화면 {screen.width}x{screen.height} → 스크린샷 {screen.shot_w}x{screen.shot_h} "
          f"(배율 {screen.scale:.3f})")

    recorder = Recorder(config.RUNS_DIR, goal)
    executor = Executor(screen, Guard(confirm=True), recorder, config.ACTION_DELAY)
    print(f"기록 폴더: {recorder.dir}")
    print("긴급 정지: 마우스를 왼쪽 위 모서리로 / Ctrl+C\n")

    try:
        result = loop.run(goal, executor, recorder)
        print(f"\n=== 결과 ({result.status}) ===\n{result.final}")
        print(f"단계 {result.steps} · 행동 {result.actions} (실패 {result.action_errors}) · "
              f"토큰 입력 {result.input_tokens:,} / 출력 {result.output_tokens:,}")
    except pyautogui.FailSafeException:
        print("\n긴급 정지되었습니다 (마우스가 화면 모서리로 이동).")
        recorder.event("abort", reason="failsafe")
    except KeyboardInterrupt:
        print("\n사용자가 중단했습니다.")
        recorder.event("abort", reason="keyboard_interrupt")
    finally:
        recorder.close()


if __name__ == "__main__":
    main()
