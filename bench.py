"""기준 성능 측정 (로드맵 4단계).

고정 과제 세트를 여러 번 실행해 성공률, 단계 수, 토큰, 시간을 기록한다.

사용법:
    uv run bench.py                       # 모든 과제 1회씩
    uv run bench.py --repeat 3            # 과제마다 3회
    uv run bench.py --tasks calc_multiply,notepad_save
    uv run bench.py --list                # 과제 목록 보기
    uv run bench.py --label baseline      # 결과 폴더 이름에 붙일 이름 (비교용)
    uv run bench.py --assist uia,wait     # 보조 도구를 켜고 측정 (기본: 끔 = 순수 computer use)
    uv run bench.py --context prune       # 컨텍스트 관리 전략 (server | prune | none)
    uv run bench.py --input directinput   # 입력 백엔드 (pyautogui | directinput)

결과: runs/bench-<시각>[-label]/
    results.jsonl   실행마다 한 줄
    summary.json    과제별/전체 요약 + 실행 조건(모델, 스크린샷 크기 등)
    <과제>-<회차>/  실행별 스크린샷과 actions.jsonl

긴급 정지: 마우스를 왼쪽 위 모서리로 / Ctrl+C (그때까지의 결과는 저장된다)
"""
import argparse
import json
import sys
import time
from pathlib import Path

# DPI 설정은 다른 GUI 모듈(pyautogui, pydirectinput)을 import 하기 전에 해야 한다
from perception.capture import enable_dpi_awareness

enable_dpi_awareness()

import config  # noqa: E402
from actions import backends  # noqa: E402
from actions.executor import Executor  # noqa: E402
from agent import context, loop  # noqa: E402
from agent.engine import get_runner  # noqa: E402
from benchmark.metrics import format_table, summarize  # noqa: E402
from benchmark.tasks import TASK_SET_VERSION, CheckContext, get_tasks  # noqa: E402
from logs.recorder import Recorder  # noqa: E402
from perception.capture import Screen  # noqa: E402
from safety.guard import Guard  # noqa: E402


def ask_success(task_id: str) -> bool | None:
    ans = input(f"  '{task_id}' 성공했나요? [y/n/s=판정 안 함] ").strip().lower()
    if ans == "s":
        return None
    return ans == "y"


def judge(task, ctx: CheckContext, result: loop.RunResult) -> tuple[bool | None, str]:
    """(성공 여부, 판정 방법)"""
    if result.status in ("aborted", "error"):
        return False, "status"
    if task.check is not None:
        try:
            verdict = task.check(ctx)
        except Exception as err:
            print(f"  자동 판정 실패: {err}")
            verdict = None
        if verdict is not None:
            return verdict, "auto"
    return ask_success(task.id), "manual"


def main() -> int:
    parser = argparse.ArgumentParser(description="pc-agent 기준 성능 측정")
    parser.add_argument("--tasks", help="쉼표로 구분한 과제 id (기본: 전체)")
    parser.add_argument("--repeat", type=int, default=1, help="과제별 반복 횟수")
    parser.add_argument("--label", default="", help="결과 폴더 이름에 붙일 이름")
    parser.add_argument("--assist", default=None,
                        help="보조 도구: uia, wait, all, none (기본: PC_AGENT_ASSIST 환경 변수)")
    parser.add_argument("--context", default=None,
                        help="컨텍스트 전략: server, prune, none (기본: PC_AGENT_CONTEXT 환경 변수)")
    parser.add_argument("--input", default=None,
                        help="입력 백엔드: pyautogui, directinput (기본: PC_AGENT_INPUT 환경 변수)")
    parser.add_argument("--engine", default=None,
                        help="엔진: sdk (구독 로그인), api (API 키) (기본: PC_AGENT_ENGINE 환경 변수)")
    parser.add_argument("--web", choices=["on", "off"], default=None,
                        help="웹 도구 WebSearch/WebFetch (sdk 엔진 전용, 기본: PC_AGENT_WEB 환경 변수)")
    parser.add_argument("--list", action="store_true", help="과제 목록만 출력")
    parser.add_argument("--no-pause", action="store_true", help="과제 사이에 Enter를 기다리지 않음")
    args = parser.parse_args()

    try:
        if args.assist is not None:
            config.ASSIST = config.parse_assist(args.assist)
        if args.context is not None:
            config.CONTEXT = args.context.strip().lower()
        context.resolve_strategy(config.CONTEXT, config.MODEL)  # 잘못된 값이면 여기서 ValueError
        if args.engine is not None:
            config.ENGINE = args.engine.strip().lower()
        if args.web is not None:
            config.WEB = args.web == "on"
        if args.input is not None:
            config.INPUT_BACKEND = args.input.strip().lower()
        if config.INPUT_BACKEND not in backends.BACKENDS:
            raise ValueError(f"알 수 없는 입력 백엔드: {config.INPUT_BACKEND} "
                             f"(사용 가능: {', '.join(backends.BACKENDS)})")
        tasks = get_tasks([t.strip() for t in args.tasks.split(",")] if args.tasks else None)
    except ValueError as err:
        print(err)
        return 2

    if args.list:
        for t in tasks:
            print(f"{t.id:22} {t.goal}")
        return 0

    try:
        run_agent, EngineError = get_runner(config.ENGINE)
    except (ValueError, ImportError) as err:
        print(f"엔진 '{config.ENGINE}'을 불러오지 못했습니다: {err}")
        return 2
    try:
        backend = backends.create(config.INPUT_BACKEND)
    except ImportError as err:
        print(f"입력 백엔드 '{config.INPUT_BACKEND}'를 불러오지 못했습니다: {err}")
        return 2
    screen = Screen(config.MAX_LONG_EDGE, config.MONITOR_INDEX)
    name = "bench-" + time.strftime("%Y%m%d-%H%M%S") + (f"-{args.label}" if args.label else "")
    out_dir = Path(config.RUNS_DIR) / name
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "label": args.label,
        "engine": config.ENGINE,
        "web": config.WEB and config.ENGINE == "sdk",
        "task_set_version": TASK_SET_VERSION,
        "model": config.MODEL,
        "max_steps": config.MAX_STEPS,
        "screen": [screen.width, screen.height],
        "screenshot": [screen.shot_w, screen.shot_h],
        "action_delay": config.ACTION_DELAY,
        "auto_screenshot": config.AUTO_SCREENSHOT,
        "assist": config.ASSIST,
        # sdk 엔진은 Claude Code가 컨텍스트를 관리하므로 아래 설정이 쓰이지 않는다
        "context": context.resolve_strategy(config.CONTEXT, config.MODEL)[0] if config.ENGINE == "api" else "claude_code",
        "prompt_cache": config.PROMPT_CACHE if config.ENGINE == "api" else None,
        "input_backend": backend.name,
        "clear": {"trigger": config.CLEAR_TRIGGER, "keep": config.CLEAR_KEEP,
                  "at_least": config.CLEAR_AT_LEAST},
        "prune": {"keep": config.PRUNE_KEEP, "batch": config.PRUNE_BATCH},
        "repeat": args.repeat,
        "tasks": [t.id for t in tasks],
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    print(f"결과 폴더: {out_dir}")
    print(f"엔진 {config.ENGINE} · 모델 {config.MODEL} · 화면 {screen.width}x{screen.height} → {screen.shot_w}x{screen.shot_h} "
          f"· 과제 {len(tasks)}개 × {args.repeat}회 · 보조 도구 {','.join(config.ASSIST) or '없음'} · 웹 {'켬' if meta['web'] else '끔'} · 컨텍스트 {meta['context']} · 입력 {backend.name}")
    print("긴급 정지: 마우스를 왼쪽 위 모서리로 / Ctrl+C\n")

    records: list[dict] = []
    results_file = open(out_dir / "results.jsonl", "a", encoding="utf-8")
    stopped = False
    try:
        for trial in range(1, args.repeat + 1):
            for task in tasks:
                print(f"\n==== [{task.id}] {trial}/{args.repeat} ====")
                print(f"목표: {task.goal}")
                if task.note:
                    print(f"준비: {task.note}")
                if not args.no_pause:
                    ans = input("준비되면 Enter (s=건너뛰기, q=종료) ").strip().lower()
                    if ans == "q":
                        stopped = True
                        break
                    if ans == "s":
                        continue
                if task.setup:
                    task.setup()

                recorder = Recorder(str(out_dir), task.goal, name=f"{task.id}-{trial}")
                executor = Executor(screen, Guard(confirm=True), recorder, config.ACTION_DELAY, backend)
                result = loop.RunResult()
                started = time.perf_counter()
                try:
                    run_agent(task.goal, executor, recorder, stats=result)
                except KeyboardInterrupt as err:
                    result.status = "aborted"
                    result.final = type(err).__name__
                    stopped = True
                except EngineError as err:
                    result.status = "error"
                    result.final = f"엔진 오류: {err}"
                    print(f"  {result.final}")
                except Exception as err:
                    if not backends.is_failsafe(err):
                        raise
                    result.status = "aborted"
                    result.final = type(err).__name__
                    stopped = True
                seconds = time.perf_counter() - started

                ctx = CheckContext(final=result.final, screen_size=(screen.width, screen.height))
                success, method = judge(task, ctx, result)
                record = {
                    "task": task.id, "trial": trial, "success": success, "judged_by": method,
                    **result.to_dict(), "seconds": round(seconds, 2),
                }
                recorder.event("bench_result", **record)
                recorder.close()
                records.append(record)
                results_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                results_file.flush()
                mark = {True: "성공", False: "실패", None: "판정 안 함"}[success]
                print(f"  → {mark} ({method}) · 상태 {result.status} · 단계 {result.steps} · "
                      f"토큰 입력 {result.input_tokens:,} + 캐시 {result.cache_read_tokens:,} / "
                      f"출력 {result.output_tokens:,} · {seconds:.1f}s")
                if stopped:
                    print("\n긴급 정지로 벤치마크를 멈춥니다.")
                    break
            if stopped:
                break
    finally:
        results_file.close()
        summary = summarize(records) if records else {"overall": None, "tasks": {}}
        meta["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump({"meta": meta, **summary}, f, ensure_ascii=False, indent=2)

    if records:
        print("\n=== 요약 ===")
        print(format_table(summary))
    print(f"\n저장: {out_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
