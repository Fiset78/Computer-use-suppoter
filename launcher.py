"""프로필 고르기 창 (tkinter).

사용법:
    uv run launcher.py

profiles/ 의 프로필을 목록에서 고르고 목표를 적은 뒤 "실행"을 누르면,
새 콘솔 창에서 `main.py --profile <이름> --no-pick "목표"`를 실행한다.
위험 행동 확인(y/n)과 실행 기록은 그 콘솔 창에 나온다. 끝나면 Enter로 창을 닫는다.

이 파일은 pyautogui를 import 하지 않는다 (DPI 설정과 입력은 main.py가 맡음).
화면(tkinter)과 상관없는 부분(entries, describe, build_command)은 순수 함수라 테스트한다.
"""
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import config
from agent import profiles

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main.py"
NO_PROFILE = "none"
PREVIEW_LINES = 12   # 상세 보기에 보여줄 prompt 줄 수


@dataclass
class Entry:
    key: str                              # 프로필 파일 이름 (프로필 없이는 "none")
    label: str                            # 목록에 보이는 이름
    profile: profiles.Profile | None = None
    error: str = ""                       # 불러오지 못했으면 그 이유


def profiles_dir(folder: str | Path = "") -> Path:
    d = Path(folder or config.PROFILES_DIR)
    return d if d.is_absolute() else ROOT / d


def entries(folder: str | Path) -> list[Entry]:
    """목록에 보일 항목. 형식이 틀린 프로필도 빼지 않고 오류와 함께 보여준다."""
    out = [Entry(NO_PROFILE, "프로필 없이 (환경 변수 설정)")]
    d = Path(folder)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.toml"), key=lambda p: p.name.lower()):
        if p.name.startswith("_"):
            continue
        try:
            prof = profiles.load(p)
        except ValueError as err:
            out.append(Entry(p.stem, f"{p.stem} (오류)", error=str(err)))
            continue
        out.append(Entry(prof.key, f"{prof.name} [{profiles.MODES[prof.mode]}]", prof))
    return out


def describe(entry: Entry) -> str:
    """오른쪽 상세 보기에 보여줄 글."""
    if entry.error:
        return f"이 프로필을 불러오지 못했습니다.\n\n{entry.error}"
    if entry.profile is None:
        return ("프로필 없이 실행합니다.\n\n"
                "Windows 조작 모드로, 환경 변수(PC_AGENT_*)에 적힌 설정을 그대로 씁니다.")
    p, data = entry.profile, entry.profile.data
    defaults = profiles.GAME_DEFAULTS if p.mode == "game" else {}

    def value(key, empty="(기본값)"):
        v = data.get(key, defaults.get(key))
        if v is None:
            return empty
        if isinstance(v, list):
            return ", ".join(str(x) for x in v) or "없음"
        return str(v)

    lines = [
        f"이름: {p.name}",
        f"파일: {p.path.name}",
        f"모드: {profiles.MODES[p.mode]}",
        f"창 제목: {value('window', '(화면 전체)')}",
        f"입력 백엔드: {value('input')}",
        f"보조 도구: {value('assist')}",
        f"지식 메모: {value('memory', '없음')}",
        f"참고 자료: {value('refs', '없음')}",
        f"최대 단계: {value('max_steps')}",
    ]
    if p.prompt:
        prompt = p.prompt.splitlines()
        lines += ["", "[안내]"] + prompt[:PREVIEW_LINES]
        if len(prompt) > PREVIEW_LINES:
            lines.append(f"... ({len(prompt) - PREVIEW_LINES}줄 더)")
    return "\n".join(lines)


def build_command(key: str, goal: str, python: str = sys.executable) -> list[str]:
    """새 콘솔에서 실행할 명령. 목표가 '-'로 시작해도 옵션으로 읽히지 않게 '--' 뒤에 둔다."""
    goal = goal.strip()
    if not goal:
        raise ValueError("목표가 비어 있습니다.")
    return [python, str(Path(__file__).resolve()), "--child",
            "--profile", key or NO_PROFILE, "--no-pick", "--", goal]


def run_child(main_args: list[str]) -> int:
    """새 콘솔 창 안에서 main.py를 돌리고, 결과를 읽을 수 있게 Enter를 기다린다."""
    code = subprocess.call([sys.executable, str(MAIN), *main_args], cwd=ROOT)
    try:
        input("\n끝났습니다. Enter를 누르면 창을 닫습니다.")
    except (EOFError, KeyboardInterrupt):
        pass
    return code


def launch(cmd: list[str]) -> None:
    # Windows: 새 콘솔 창 (위험 행동 y/n 확인을 거기서 받는다). 다른 OS에는 이 플래그가 없다.
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(cmd, cwd=ROOT, creationflags=flags)


def open_file(path: Path) -> None:
    if sys.platform == "win32":
        import os
        os.startfile(path)  # 기본 편집기로 연다
    else:
        subprocess.Popen(["xdg-open", str(path)])


# ---------- 창 ----------
def gui() -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    folder = profiles_dir()
    root = tk.Tk()
    root.title("pc-agent 프로필 고르기")
    root.geometry("820x520")
    root.minsize(640, 400)

    state = {"entries": []}

    frame = ttk.Frame(root, padding=10)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)
    frame.rowconfigure(1, weight=1)

    ttk.Label(frame, text=f"프로필 ({folder.name}/)").grid(row=0, column=0, sticky="w")
    ttk.Label(frame, text="설정").grid(row=0, column=1, sticky="w", padx=(10, 0))

    listbox = tk.Listbox(frame, exportselection=False, width=32, activestyle="none")
    listbox.grid(row=1, column=0, sticky="ns")
    detail = tk.Text(frame, wrap="word", state="disabled", relief="flat", background=root.cget("background"),
                     font="TkDefaultFont")
    detail.grid(row=1, column=1, sticky="nsew", padx=(10, 0))

    ttk.Label(frame, text="목표").grid(row=2, column=0, sticky="w", pady=(10, 0))
    goal = ttk.Entry(frame)
    goal.grid(row=3, column=0, columnspan=2, sticky="ew")

    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))

    def selected() -> Entry | None:
        sel = listbox.curselection()
        return state["entries"][sel[0]] if sel else None

    def show(_event=None):
        entry = selected()
        detail.configure(state="normal")
        detail.delete("1.0", "end")
        detail.insert("1.0", describe(entry) if entry else "")
        detail.configure(state="disabled")

    def refresh(keep: str = ""):
        keep = keep or (selected().key if selected() else config.PROFILE or NO_PROFILE)
        state["entries"] = entries(folder)
        listbox.delete(0, "end")
        index = 0
        for i, e in enumerate(state["entries"]):
            listbox.insert("end", e.label)
            if e.key == keep:
                index = i
        listbox.selection_set(index)
        listbox.see(index)
        show()

    def run(_event=None):
        entry = selected()
        if entry is None:
            return
        if entry.error:
            messagebox.showerror("프로필 오류", entry.error)
            return
        try:
            cmd = build_command(entry.key, goal.get())
        except ValueError as err:
            messagebox.showwarning("목표", str(err))
            goal.focus_set()
            return
        launch(cmd)

    def edit():
        entry = selected()
        if entry is None or entry.key == NO_PROFILE:
            messagebox.showinfo("프로필 파일", "프로필을 먼저 고르세요.")
            return
        open_file(folder / f"{entry.key}.toml")

    ttk.Button(buttons, text="프로필 파일 열기", command=edit).pack(side="left")
    ttk.Button(buttons, text="새로고침", command=refresh).pack(side="left", padx=(6, 0))
    ttk.Button(buttons, text="실행", command=run).pack(side="left", padx=(6, 0))

    listbox.bind("<<ListboxSelect>>", show)
    listbox.bind("<Double-Button-1>", lambda _e: goal.focus_set())
    goal.bind("<Return>", run)

    refresh()
    goal.focus_set()
    root.mainloop()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        sys.exit(run_child(sys.argv[2:]))
    gui()


if __name__ == "__main__":
    main()
