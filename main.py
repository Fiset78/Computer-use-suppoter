"""진입점.

사용법:
    uv run main.py "메모장을 열고 '안녕하세요'라고 입력해줘"
    uv run main.py            # 실행 후 목표를 입력
    uv run main.py --memory memory/mc.md --ref refs/조작법.md --ref refs/제작법.png "목표"
    uv run main.py --profile minecraft "나무 4개 모아줘"   # 프로필로 실행 (게임/Windows 조작 선택)
    uv run main.py --new-profile 테라리아 --mode game --window Terraria   # 새 프로필 만들기
    uv run main.py --no-pick "목표"   # 시작 메뉴 없이 바로 실행

시작할 때 프로필(무엇을 조작할지) → 지식 메모 → 참고 자료를 번호로 고르는 메뉴가 나온다.

긴급 정지: F12(PC_AGENT_KILL_KEY), 마우스를 화면 왼쪽 위 모서리로, 또는 터미널에서 Ctrl+C
"""
import sys
from pathlib import Path

# DPI 설정은 다른 GUI 모듈(pyautogui, pydirectinput)을 import 하기 전에 해야 한다
from perception.capture import enable_dpi_awareness

enable_dpi_awareness()

import config  # noqa: E402
from actions import backends  # noqa: E402
from actions.executor import Executor  # noqa: E402
from agent import context, loop, profiles, refs  # noqa: E402
from logs.recorder import Recorder  # noqa: E402
from perception.capture import Screen  # noqa: E402
from safety.guard import Guard  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="pc-agent: Claude가 화면을 보고 PC를 조작")
    parser.add_argument("goal", nargs="*", help="목표 (생략하면 실행 후 입력)")
    parser.add_argument("--profile", help="프로필 이름 또는 .toml 경로 (none이면 프로필 없이, 기본: PC_AGENT_PROFILE)")
    parser.add_argument("--new-profile", metavar="이름", help="profiles/<이름>.toml 템플릿을 만들고 끝냄")
    parser.add_argument("--mode", choices=list(profiles.MODES), default="game",
                        help="--new-profile과 함께: desktop(Windows 조작) 또는 game(게임 조작). 기본 game")
    parser.add_argument("--window", default="", help="--new-profile과 함께: 게임 창 제목")
    parser.add_argument("--memory", help="지식 메모 파일 (none이면 끔, 기본: PC_AGENT_MEMORY)")
    parser.add_argument("--ref", action="append", default=None,
                        help="참고 자료 파일. 여러 번 쓸 수 있음 (기본: PC_AGENT_REFS)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pick", action="store_true", help="시작 메뉴를 항상 보여줌")
    group.add_argument("--no-pick", action="store_true", help="시작 메뉴를 보여주지 않음")
    return parser.parse_args(argv)


def choose_profile(args: argparse.Namespace, interactive: bool) -> None:
    """프로필을 고르고(명령줄 > 시작 메뉴 > PC_AGENT_PROFILE) config에 적용한다."""
    chosen = None
    if args.profile is not None:
        if args.profile.strip().lower() not in ("", "none"):
            chosen = profiles.load(profiles.find(args.profile.strip(), config.PROFILES_DIR))
    elif interactive:
        chosen = profiles.pick(config.PROFILES_DIR, config.PROFILE)
    elif config.PROFILE:
        chosen = profiles.load(profiles.find(config.PROFILE, config.PROFILES_DIR))
    if chosen is None:
        print("\n프로필: 없음 (Windows 조작, 환경 변수 설정)")
        return
    applied = profiles.apply(chosen, config)
    print(f"\n프로필: {chosen.name} [{profiles.MODES[chosen.mode]}] ({chosen.path})"
          + (f" · 적용: {', '.join(applied)}" if applied else ""))


def interactive_menu(args: argparse.Namespace) -> bool:
    has_files = bool(profiles.list_profiles(config.PROFILES_DIR)
                     or refs.candidates(config.MEMORY_DIR, memory=True) or refs.candidates(config.REFS_DIR))
    return args.pick or (not args.no_pick and sys.stdin.isatty() and has_files)


def choose_files(args: argparse.Namespace, interactive: bool = False) -> None:
    """명령줄 옵션을 config에 반영하고, 필요하면 시작 메뉴로 메모·참고 자료를 고르게 한다.
    프로필을 먼저 적용한 뒤 부른다 (프로필의 메모·참고 자료가 메뉴의 기본값이 된다)."""
    if args.memory is not None:
        config.MEMORY_FILE = "" if args.memory.strip().lower() in ("", "none") else args.memory.strip()
    if args.ref is not None:
        config.REFS = [p for r in args.ref for p in refs.parse_paths(r)]
    if interactive and (args.memory is None or args.ref is None):
        config.MEMORY_FILE, config.REFS = refs.pick(config.MEMORY_DIR, config.REFS_DIR,
                                                    config.MEMORY_FILE, config.REFS)
    print(f"\n지식 메모: {config.MEMORY_FILE or '없음'} · 참고 자료: "
          f"{', '.join(config.REFS) if config.REFS else '없음'}")


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] in ("-f", "--file"):
        # 긴 목표(여러 줄 프롬프트)는 파일로 넘긴다: uv run main.py -f prompts\minecraft_controls.txt
        try:
            goal = Path(args[1]).read_text(encoding="utf-8-sig").strip()
        except OSError as err:
            print(f"목표 파일을 읽지 못했습니다: {err}")
            return
        print(f"프로필을 만들었습니다: {path}\n파일을 열어 조작법(prompt)과 설정을 채운 뒤 "
              f"uv run main.py --profile {args.new_profile} \"목표\" 로 실행하세요.")
        return
    goal = " ".join(args.goal).strip() or input("목표를 입력하세요: ").strip()
    if not goal:
        print("목표가 비어 있습니다.")
        return
    # 게임 창으로 포커스를 옮기기 전에 고른다 (메뉴 입력이 터미널에 들어가야 하므로)
    interactive = interactive_menu(args)
    try:
        choose_profile(args, interactive)
    except (ValueError, OSError) as err:
        print(f"프로필을 불러오지 못했습니다: {err}")
        return
    choose_files(args, interactive)

    try:
        context.resolve_strategy(config.CONTEXT, config.MODEL)
        run_agent, _ = get_runner(config.ENGINE)
        backend = backends.create(config.INPUT_BACKEND)
    except (ValueError, ImportError) as err:
        print(err)
        return

    screen = Screen(config.MAX_LONG_EDGE, config.MONITOR_INDEX)
    print(f"화면 {screen.width}x{screen.height} → 스크린샷 {screen.shot_w}x{screen.shot_h} "
          f"(배율 {screen.scale:.3f})")

    recorder = Recorder(config.RUNS_DIR, goal)
    executor = Executor(screen, Guard(confirm=True), recorder, config.ACTION_DELAY, backend)
    print(f"기록 폴더: {recorder.dir}")
    context_label = config.CONTEXT if config.ENGINE == "api" else "Claude Code 자동 관리"
    if config.WEB and config.ENGINE != "sdk":
        print("주의: 웹 도구(PC_AGENT_WEB)는 sdk 엔진에서만 쓸 수 있어서 무시합니다.")
    web_label = "켬" if config.WEB and config.ENGINE == "sdk" else "끔"
    print(f"엔진: {config.ENGINE} · 보조 도구: {', '.join(config.ASSIST) or '없음 (순수 computer use)'} · "
          f"웹 도구: {web_label} · 컨텍스트 전략: {context_label} · 입력 백엔드: {backend.name}")
    print("긴급 정지: 마우스를 왼쪽 위 모서리로 / Ctrl+C\n")

    try:
        result = run_chain(run_agent, goal, executor, recorder, config.MAX_CHAIN)
        print(f"\n=== 결과 ({result.status}) ===\n{result.final}")
        print(f"단계 {result.steps} · 행동 {result.actions} (실패 {result.action_errors}) · "
              f"토큰 입력 {result.input_tokens:,} + 캐시 읽기 {result.cache_read_tokens:,} "
              f"/ 캐시 쓰기 {result.cache_write_tokens:,} / 출력 {result.output_tokens:,}")
    except KeyboardInterrupt:
        print("\n사용자가 중단했습니다.")
        recorder.event("abort", reason="keyboard_interrupt")
    except Exception as err:
        if not backends.is_failsafe(err):
            raise
        print("\n긴급 정지되었습니다 (마우스가 화면 모서리로 이동).")
        recorder.event("abort", reason="failsafe")
    finally:
        recorder.close()


if __name__ == "__main__":
    main()
