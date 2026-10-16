"""진입점.

사용법:
    uv run main.py "메모장을 열고 '안녕하세요'라고 입력해줘"
    uv run main.py            # 실행 후 목표를 입력

긴급 정지: F12(PC_AGENT_KILL_KEY), 마우스를 화면 왼쪽 위 모서리로, 또는 터미널에서 Ctrl+C
"""
import sys

# DPI 설정은 다른 GUI 모듈(pyautogui, pydirectinput)을 import 하기 전에 해야 한다
from perception.capture import enable_dpi_awareness

enable_dpi_awareness()

import config  # noqa: E402
from actions import backends  # noqa: E402
from actions.assist import backend_warning  # noqa: E402
from actions.executor import Executor  # noqa: E402
from agent import context, loop  # noqa: E402
from logs.recorder import Recorder  # noqa: E402
from perception import window  # noqa: E402
from safety import killswitch  # noqa: E402
from safety.guard import Guard  # noqa: E402


def main() -> None:
    goal = " ".join(sys.argv[1:]).strip() or input("목표를 입력하세요: ").strip()
    if not goal:
        print("목표가 비어 있습니다.")
        return

    try:
        context.resolve_strategy(config.CONTEXT, config.MODEL)
        if config.KILL_KEY:
            killswitch.vk_code(config.KILL_KEY)  # 잘못된 키면 시작 전에 알린다
        backend = backends.create(config.INPUT_BACKEND)
        screen, win = window.open_screen(config.MAX_LONG_EDGE, config.MONITOR_INDEX, config.WINDOW)
    except (ValueError, ImportError, LookupError) as err:
        print(err)
        return

    if win:
        print(f"캡처 창: \"{win.title}\" ({win.rect[0]},{win.rect[1]}) — 이 창만 보고 조작합니다")
    print(f"화면 {screen.width}x{screen.height} → 스크린샷 {screen.shot_w}x{screen.shot_h} "
          f"(배율 {screen.scale:.3f})")

    recorder = Recorder(config.RUNS_DIR, goal)
    guard = Guard(confirm=True)
    executor = Executor(screen, guard, recorder, config.ACTION_DELAY, backend)
    if win:
        executor.focus_hwnd = win.hwnd
        guard.after_prompt = executor.ensure_focus
    print(f"기록 폴더: {recorder.dir}")
    print(f"보조 도구: {', '.join(config.ASSIST) or '없음 (순수 computer use)'} · "
          f"컨텍스트 전략: {config.CONTEXT} · 입력 백엔드: {backend.name}")
    if warning := backend_warning(config.ASSIST, backend.name):
        print(warning)
    watcher = killswitch.start_hotkey(config.KILL_KEY, on_trigger=backend.release_all)
    print(killswitch.stop_hint(watcher) + "\n")

    try:
        result = loop.run(goal, executor, recorder)
        print(f"\n=== 결과 ({result.status}) ===\n{result.final}")
        print(f"단계 {result.steps} · 행동 {result.actions} (실패 {result.action_errors}) · "
              f"토큰 입력 {result.input_tokens:,} + 캐시 읽기 {result.cache_read_tokens:,} "
              f"/ 캐시 쓰기 {result.cache_write_tokens:,} / 출력 {result.output_tokens:,}")
    except killswitch.EmergencyStop:
        print("\n긴급 정지 단축키로 멈췄습니다.")
        recorder.event("abort", reason="kill_switch")
    except KeyboardInterrupt:
        print("\n사용자가 중단했습니다.")
        recorder.event("abort", reason="keyboard_interrupt")
    except Exception as err:
        if not backends.is_failsafe(err):
            raise
        print("\n긴급 정지되었습니다 (마우스가 화면 모서리로 이동).")
        recorder.event("abort", reason="failsafe")
    finally:
        released = backend.release_all()  # 눌린 채로 남은 키/버튼이 없게
        if released:
            recorder.event("release_all", inputs=released)
        if watcher:
            watcher.stop()
        recorder.close()


if __name__ == "__main__":
    main()
