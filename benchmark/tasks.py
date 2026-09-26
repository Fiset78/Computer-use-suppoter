"""고정 과제 세트.

같은 과제를 같은 조건에서 반복해야 보조 기능 전후를 비교할 수 있다.
- setup: 실행 전 상태 초기화 (전용 작업 폴더 BENCH_DIR 안의 파일만 건드린다)
- check: 실행 후 자동 성공 판정. None을 반환하거나 check가 없으면 사람이 y/n으로 판정한다.
- note: 시작 전에 사용자에게 보여줄 준비 안내
과제 목록을 바꾸면 이전 결과와 비교할 수 없으므로, 수정 대신 새 과제를 추가하고 TASK_SET_VERSION을 올린다.
"""
import ctypes
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

TASK_SET_VERSION = 1

# 벤치마크 전용 작업 폴더. setup은 이 폴더 안만 지운다.
BENCH_DIR = Path.home() / "pc-agent-bench"


@dataclass
class CheckContext:
    final: str                    # Claude의 완료 보고
    screen_size: tuple[int, int]  # 실제 화면 해상도 (물리 픽셀)


@dataclass
class Task:
    id: str
    goal: str
    setup: Callable[[], None] | None = None
    check: Callable[[CheckContext], bool | None] | None = None
    note: str = ""


# ---------- 공통 도우미 ----------
def _reset_bench_dir(*names: str) -> None:
    BENCH_DIR.mkdir(exist_ok=True)
    for name in names:
        p = BENCH_DIR / name
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()


def _foreground_title() -> str:
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def _clipboard() -> str:
    import pyperclip
    try:
        return pyperclip.paste() or ""
    except Exception:
        return ""


def _set_clipboard(text: str) -> None:
    import pyperclip
    pyperclip.copy(text)


def _digits(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())


# ---------- 과제 ----------
NOTE_FILE = "hello.txt"
NOTE_TEXT = "pc-agent 벤치마크"
FOLDER_NAME = "벤치폴더"


def _check_note(ctx: CheckContext) -> bool:
    p = BENCH_DIR / NOTE_FILE
    if not p.exists():
        return False
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp949"):
        try:
            return NOTE_TEXT in raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return False


def _check_calc(ctx: CheckContext) -> bool:
    # 계산기는 "5,535"처럼 구분 기호를 붙여 복사할 수 있으므로 숫자만 비교
    return _digits(_clipboard()) == "5535"


def _check_documents(ctx: CheckContext) -> bool | None:
    title = _foreground_title()
    if not title:
        return None  # 판정 불가 → 사람이 확인
    return "문서" in title or "Documents" in title


def _check_folder(ctx: CheckContext) -> bool:
    return (BENCH_DIR / FOLDER_NAME).is_dir()


def _check_resolution(ctx: CheckContext) -> bool:
    w, h = ctx.screen_size
    digits = _digits(ctx.final.replace(",", ""))
    return str(w) in digits and str(h) in digits


TASKS: list[Task] = [
    Task(
        id="notepad_save",
        goal=(f"메모장을 열고 새 문서에 '{NOTE_TEXT}'라고 입력한 뒤, "
              f"{BENCH_DIR / NOTE_FILE} 경로에 저장해줘."),
        setup=lambda: _reset_bench_dir(NOTE_FILE),
        check=_check_note,
        note="메모장이 열려 있으면 닫아 주세요.",
    ),
    Task(
        id="calc_multiply",
        goal="계산기를 열어서 123 곱하기 45를 계산하고, 결과를 Ctrl+C로 클립보드에 복사해줘.",
        setup=lambda: _set_clipboard(""),
        check=_check_calc,
        note="계산기가 열려 있으면 닫아 주세요.",
    ),
    Task(
        id="explorer_documents",
        goal="파일 탐색기에서 문서 폴더를 열어줘.",
        check=_check_documents,
        note="파일 탐색기 창을 모두 닫아 주세요.",
    ),
    Task(
        id="explorer_new_folder",
        goal=f"파일 탐색기로 {BENCH_DIR} 폴더에 들어가서 '{FOLDER_NAME}'라는 새 폴더를 만들어줘.",
        setup=lambda: _reset_bench_dir(FOLDER_NAME),
        check=_check_folder,
        note="파일 탐색기 창을 모두 닫아 주세요.",
    ),
    Task(
        id="settings_resolution",
        goal="Windows 설정 앱에서 현재 디스플레이 해상도를 확인하고, 해상도 숫자를 알려줘.",
        check=_check_resolution,
        note="설정 앱이 열려 있으면 닫아 주세요.",
    ),
]


def get_tasks(ids: list[str] | None = None) -> list[Task]:
    if not ids:
        return list(TASKS)
    by_id = {t.id: t for t in TASKS}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise ValueError(f"알 수 없는 과제: {', '.join(unknown)} (사용 가능: {', '.join(by_id)})")
    return [by_id[i] for i in ids]
