"""진입점.

사용법:
    uv run main.py "메모장을 열고 '안녕하세요'라고 입력해줘"
    uv run main.py            # 실행 후 목표를 입력
    uv run main.py --memory memory/mc.md --ref refs/조작법.md --ref refs/제작법.png "목표"
    uv run main.py --no-pick "목표"   # 시작 메뉴(메모·참고 자료 고르기) 없이 바로 실행

memory/ 또는 refs/ 폴더에 파일이 있으면 시작할 때 쓸 파일을 번호로 고르는 메뉴가 나온다.

긴급 정지: F12(PC_AGENT_KILL_KEY), 마우스를 화면 왼쪽 위 모서리로, 또는 터미널에서 Ctrl+C
"""
import argparse
import sys

# DPI 설정은 다른 GUI 모듈(pyautogui, pydirectinput)을 import 하기 전에 해야 한다
from perception.capture import enable_dpi_awareness

enable_dpi_awareness()

import config  # noqa: E402
from actions import backends  # noqa: E402
from actions.assist import backend_warning  # noqa: E402
from actions.executor import Executor  # noqa: E402
from agent import context, loop, refs  # noqa: E402
from logs.recorder import Recorder  # noqa: E402
from perception import window  # noqa: E402
from safety import killswitch  # noqa: E402
from safety.guard import Guard  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="pc-agent: Claude가 화면을 보고 PC를 조작")
    parser.add_argument("goal", nargs="*", help="목표 (생략하면 실행 후 입력)")
    parser.add_argument("--memory", help="지식 메모 파일 (none이면 끔, 기본: PC_AGENT_MEMORY)")
    parser.add_argument("--ref", action="append", default=None,
                        help="참고 자료 파일. 여러 번 쓸 수 있음 (기본: PC_AGENT_REFS)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pick", action="store_true", help="시작 메뉴를 항상 보여줌")
    group.add_argument("--no-pick", action="store_true", help="시작 메뉴를 보여주지 않음")
    return parser.parse_args(argv)


def choose_files(args: argparse.Namespace) -> None:
    """명령줄 옵션을 config에 반영하고, 필요하면 시작 메뉴로 메모·참고 자료를 고르게 한다."""
    if args.memory is not None:
        config.MEMORY_FILE = "" if args.memory.strip().lower() in ("", "none") else args.memory.strip()
    if args.ref is not None:
        config.REFS = [p for r in args.ref for p in refs.parse_paths(r)]
    has_files = bool(refs.candidates(config.MEMORY_DIR, memory=True) or refs.candidates(config.REFS_DIR))
    if args.pick or (not args.no_pick and sys.stdin.isatty() and has_files):
        config.MEMORY_FILE, config.REFS = refs.pick(config.MEMORY_DIR, config.REFS_DIR,
                                                    config.MEMORY_FILE, config.REFS)
    print(f"\n지식 메모: {config.MEMORY_FILE or '없음'} · 참고 자료: "
          f"{', '.join(config.REFS) if config.REFS else '없음'}")


def main() -> None:
    args = parse_args(sys.argv[1:])
    goal = " ".join(args.goal).strip() or input("목표를 입력하세요: ").strip()
    if not goal:
        print("목표가 비어 있습니다.")
        return
    # 게임 창으로 포커스를 옮기기 전에 고른다 (메뉴 입력이 터미널에 들어가야 하므로)
    choose_files(args)

    try:
        context.resolve_strategy(config.CONTEXT, config.MODEL)
        if config.KILL_KEY:
            killswitch.vk_code(config.KILL_KEY)  # 잘못된 키면 시작 전에 알린다
        backend = backends.create(config.INPUT_BACKEND, click_settle=config.CLICK_SETTLE,
                                  click_hold=config.CLICK_HOLD)
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
