"""Windows PC 자가 점검. 마우스/키보드를 움직이지 않는 안전한 확인만 한다.

사용법:
    uv run selfcheck.py          # API 없이 로컬 기능만 점검
    uv run selfcheck.py --api    # + API 키와 computer_toolset 요청이 받아들여지는지 (아주 작은 요청 1회)

결과: 터미널에 항목별 OK/실패/건너뜀, runs/selfcheck-<시각>/ 에 캡처 이미지와 결과(JSON)
"""
import argparse
import json
import os
import platform
import sys
import time
import traceback
from pathlib import Path

# DPI 설정은 다른 GUI 모듈(pyautogui, pydirectinput)을 import 하기 전에 해야 한다
from perception.capture import enable_dpi_awareness

enable_dpi_awareness()

import config  # noqa: E402

OK, FAIL, SKIP = "OK", "실패", "건너뜀"
results: list[dict] = []


def check(name: str, windows_only: bool = False):
    def deco(fn):
        def run(*args):
            if windows_only and sys.platform != "win32":
                results.append({"name": name, "status": SKIP, "detail": "Windows 전용"})
                return None
            try:
                detail = fn(*args)
                results.append({"name": name, "status": OK, "detail": detail or ""})
                return detail
            except (Exception, SystemExit) as err:  # 일부 라이브러리는 import 실패 시 sys.exit를 부른다
                results.append({"name": name, "status": FAIL, "detail": f"{type(err).__name__}: {err}",
                                "trace": traceback.format_exc(limit=3)})
                return None
        return run
    return deco


@check("DPI 인식", windows_only=True)
def c_dpi():
    import ctypes
    awareness = ctypes.c_int()
    ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
    scale = ctypes.windll.shcore.GetScaleFactorForDevice(0)
    if awareness.value == 0:
        raise RuntimeError("DPI 인식이 꺼져 있습니다. 배율이 100%가 아니면 클릭이 어긋납니다.")
    return f"awareness={awareness.value} (2=모니터별), 디스플레이 배율 {scale}%"


@check("화면 캡처와 축소")
def c_capture(out_dir: Path):
    from perception.capture import Screen
    screen = Screen(config.MAX_LONG_EDGE, config.MONITOR_INDEX)
    img = screen.capture()
    img.save(out_dir / "capture.png")
    if img.size != (screen.shot_w, screen.shot_h):
        raise RuntimeError(f"캡처 크기 {img.size} != 예상 {(screen.shot_w, screen.shot_h)}")
    if img.getextrema() in (((0, 0), (0, 0), (0, 0)),):
        raise RuntimeError("캡처가 완전히 검은 화면입니다.")
    # 좌표 변환 왕복 확인
    for x, y in [(0, 0), (screen.shot_w - 1, screen.shot_h - 1), (screen.shot_w // 2, screen.shot_h // 2)]:
        bx, by = screen.to_shot(*screen.to_screen(x, y))
        if abs(bx - x) > 1 or abs(by - y) > 1:
            raise RuntimeError(f"좌표 왕복 오차: {(x, y)} → {(bx, by)}")
    return (f"모니터 {config.MONITOR_INDEX}: {screen.width}x{screen.height} → 스크린샷 "
            f"{screen.shot_w}x{screen.shot_h} (배율 {screen.scale:.3f}), capture.png 저장")


@check("pyautogui 백엔드")
def c_pyautogui():
    from actions import backends
    b = backends.create("pyautogui")
    x, y = b.position()
    b.check_keys(["ctrl", "shift", "alt", "win", "enter", "hangul"])
    return f"커서 위치 ({x},{y}), 주요 키 이름 지원"


@check("directinput 백엔드 (게임용)", windows_only=True)
def c_directinput():
    from actions import backends
    b = backends.create("directinput")
    x, y = b.position()
    missing = [k for k in ["ctrl", "shift", "alt", "win", "enter", "w", "a", "s", "d", "space", "esc"]
               if not b.is_valid_key(k)]
    if missing:
        raise RuntimeError(f"지원하지 않는 키: {missing}")
    return f"커서 위치 ({x},{y}), 게임 이동 키 지원 (한/영 키는 미지원)"


@check("클립보드 (한글 입력용)")
def c_clipboard():
    import pyperclip
    backup = pyperclip.paste()
    try:
        pyperclip.copy("안녕하세요 pc-agent")
        got = pyperclip.paste()
    finally:
        pyperclip.copy(backup)
    if got != "안녕하세요 pc-agent":
        raise RuntimeError(f"읽은 값이 다릅니다: {got!r}")
    return "한글 복사/읽기 정상, 원래 클립보드 복원"


@check("UI Automation 요소 목록", windows_only=True)
def c_uia():
    from perception import uia
    from perception.capture import Screen
    from perception.elements import filter_elements, format_elements
    screen = Screen(config.MAX_LONG_EDGE, config.MONITOR_INDEX)
    window = uia.foreground_window()
    if window is None:
        raise RuntimeError("활성 창을 찾지 못했습니다.")
    started = time.perf_counter()
    raw = uia.collect(window)
    seconds = time.perf_counter() - started
    shown = filter_elements(raw, in_view=lambda x, y: screen.in_bounds(*screen.to_shot(x, y)))
    preview = format_elements(shown[:8], screen.to_shot, window.Name or "", len(shown))
    print("\n    [UIA 미리보기: 지금 활성 창 = 이 터미널]\n    " + preview.replace("\n", "\n    "))
    return f"활성 창 '{window.Name}': 요소 {len(raw)}개 수집, 표시 대상 {len(shown)}개, {seconds:.2f}초"


@check("화면 변화 감지 (1초, 변화 없어야 정상)")
def c_wait():
    from perception import diff
    from perception.capture import Screen
    screen = Screen(config.MAX_LONG_EDGE, config.MONITOR_INDEX)
    base = screen.capture()
    r = diff.wait_for_change(screen.capture, base, timeout=1.0)
    return r.describe() + (" (시계, 애니메이션 등 움직이는 화면이 있으면 변화로 나올 수 있음)" if r.changed else "")


@check("설정값")
def c_config():
    from agent import context
    strategy, warning = context.resolve_strategy(config.CONTEXT, config.MODEL)
    return (f"모델 {config.MODEL}, 보조 도구 {config.ASSIST or '없음'}, 컨텍스트 {strategy}"
            f"{' (' + warning + ')' if warning else ''}, 입력 {config.INPUT_BACKEND}")


@check("API 요청 (computer_toolset_20260801)")
def c_api():
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY 환경 변수가 없습니다.")
    from anthropic import Anthropic
    resp = Anthropic().messages.create(
        model=config.MODEL,
        max_tokens=1024,
        tools=[{"type": "computer_toolset_20260801"}],
        messages=[{"role": "user", "content": "도구를 쓰지 말고 'OK'라고만 답하세요."}],
    )
    text = " ".join(b.text for b in resp.content if b.type == "text").strip()
    return (f"모델 {resp.model} 응답 '{text[:30]}', stop_reason={resp.stop_reason}, "
            f"입력 {resp.usage.input_tokens} / 출력 {resp.usage.output_tokens} 토큰")


def main() -> int:
    parser = argparse.ArgumentParser(description="pc-agent 자가 점검 (마우스/키보드를 움직이지 않음)")
    parser.add_argument("--api", action="store_true", help="API 키와 toolset 요청도 확인 (아주 작은 요청 1회)")
    args = parser.parse_args()

    out_dir = Path(config.RUNS_DIR) / ("selfcheck-" + time.strftime("%Y%m%d-%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"pc-agent 자가 점검 · {platform.platform()} · Python {platform.python_version()}\n")

    c_dpi()
    c_capture(out_dir)
    c_pyautogui()
    c_directinput()
    c_clipboard()
    c_uia()
    c_wait()
    c_config()
    if args.api:
        c_api()
    else:
        results.append({"name": "API 요청", "status": SKIP, "detail": "--api로 실행하면 확인"})

    print()
    for r in results:
        print(f"[{r['status']:^4}] {r['name']}: {r['detail']}")
    with open(out_dir / "selfcheck.json", "w", encoding="utf-8") as f:
        json.dump({"platform": platform.platform(), "python": platform.python_version(), "results": results},
                  f, ensure_ascii=False, indent=2)
    failed = [r for r in results if r["status"] == FAIL]
    print(f"\n{len(results) - len(failed)}/{len(results)} 통과 · 결과: {out_dir / 'selfcheck.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
