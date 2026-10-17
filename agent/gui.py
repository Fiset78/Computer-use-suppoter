"""시작 창 (tkinter): 프로필 → 지식 메모 → 참고 자료 → 목표를 한 화면에서 고른다.

main.py가 목표 없이 실행되면 이 창을 띄운다 (터미널 시작 메뉴 대신).
창을 닫으면 같은 콘솔에서 바로 에이전트가 시작된다. 게임 창 포커스(window.open_screen)보다 먼저 부른다.

화면(tkinter)과 상관없는 부분(entries, describe, *_options, profile_files)은 순수 함수라 테스트한다.
tkinter는 choose() 안에서만 import 한다.
"""
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from agent import profiles, refs

NO_PROFILE = "none"
NO_MEMORY = "쓰지 않음"
PREVIEW_LINES = 12   # 상세 보기에 보여줄 prompt 줄 수


@dataclass
class Entry:
    key: str                              # 프로필 파일 이름 (프로필 없이는 "none")
    label: str                            # 목록에 보이는 이름
    profile: profiles.Profile | None = None
    error: str = ""                       # 불러오지 못했으면 그 이유


@dataclass
class Selection:
    profile: profiles.Profile | None
    memory: str                           # "" 이면 지식 메모를 쓰지 않음
    refs: list[str] = field(default_factory=list)
    goal: str = ""


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
        f"최대 단계: {value('max_steps')}",
    ]
    if p.prompt:
        prompt = p.prompt.splitlines()
        lines += ["", "[안내]"] + prompt[:PREVIEW_LINES]
        if len(prompt) > PREVIEW_LINES:
            lines.append(f"... ({len(prompt) - PREVIEW_LINES}줄 더)")
    return "\n".join(lines)


def profile_files(profile: profiles.Profile | None, base_memory: str, base_refs) -> tuple[str, list[str]]:
    """이 프로필을 적용하면 정해지는 (지식 메모, 참고 자료). 프로필에 없으면 base(환경 변수) 값."""
    data = profile.data if profile else {}
    memory = str(data.get("memory", base_memory))
    chosen = [str(r) for r in data.get("refs", base_refs)]
    return memory, chosen


def memory_options(memory_dir: str | Path, current: str = "") -> list[str]:
    """메모 선택 칸의 항목: memory/ 의 .md 파일 + 프로필이 정한 파일(아직 없어도)."""
    out = [str(p) for p in refs.candidates(memory_dir, memory=True)]
    if current and not any(Path(current) == Path(o) for o in out):
        out.append(current)
    return out


def ref_options(refs_dir: str | Path, current=()) -> list[str]:
    """참고 자료 목록: refs/ 의 파일 + 프로필이 정한 파일(하위 폴더 등)."""
    out = [str(p) for p in refs.candidates(refs_dir)]
    for r in current:
        if not any(Path(r) == Path(o) for o in out):
            out.append(str(r))
    return out


def open_file(path: Path) -> None:
    if sys.platform == "win32":
        import os
        os.startfile(path)  # 기본 편집기로 연다
    else:
        subprocess.Popen(["xdg-open", str(path)])


# ---------- 창 ----------
def choose(profiles_dir: str | Path, memory_dir: str | Path, refs_dir: str | Path, current_profile: str = "",
           base_memory: str = "", base_refs=(), goal: str = "") -> Selection | None:
    """창을 띄워 고르게 한다. 시작을 누르면 Selection, 창을 닫거나 취소하면 None.
    tkinter가 없으면 ImportError를 그대로 던진다 (main이 터미널 메뉴로 넘어감)."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    folder = Path(profiles_dir)
    result: dict = {"selection": None}
    state: dict = {"entries": [], "memories": [], "refs": []}

    root = tk.Tk()
    root.title("pc-agent 시작")
    root.geometry("860x640")
    root.minsize(680, 520)

    frame = ttk.Frame(root, padding=10)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)
    frame.rowconfigure(1, weight=1)

    ttk.Label(frame, text=f"프로필 ({folder.name}/) — 무엇을 조작할지").grid(row=0, column=0, sticky="w")
    ttk.Label(frame, text="설정").grid(row=0, column=1, sticky="w", padx=(10, 0))
    listbox = tk.Listbox(frame, exportselection=False, width=32, activestyle="none")
    listbox.grid(row=1, column=0, sticky="ns")
    detail = tk.Text(frame, wrap="word", state="disabled", relief="flat", height=14,
                     background=root.cget("background"), font="TkDefaultFont")
    detail.grid(row=1, column=1, sticky="nsew", padx=(10, 0))

    ttk.Label(frame, text=f"지식 메모 ({memory_dir}/) — Claude가 읽고 고치는 파일").grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
    memory_box = ttk.Combobox(frame, state="readonly")
    memory_box.grid(row=3, column=0, columnspan=2, sticky="ew")

    ttk.Label(frame, text=f"참고 자료 ({refs_dir}/) — 읽기 전용, Ctrl/Shift+클릭으로 여러 개").grid(
        row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
    ref_list = tk.Listbox(frame, selectmode="extended", exportselection=False, height=4, activestyle="none")
    ref_list.grid(row=5, column=0, columnspan=2, sticky="ew")

    ttk.Label(frame, text="목표").grid(row=6, column=0, sticky="w", pady=(10, 0))
    goal_entry = ttk.Entry(frame)
    goal_entry.grid(row=7, column=0, columnspan=2, sticky="ew")
    goal_entry.insert(0, goal)

    buttons = ttk.Frame(frame)
    buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(10, 0))

    def selected() -> Entry | None:
        sel = listbox.curselection()
        return state["entries"][sel[0]] if sel else None

    def fill_files(entry: Entry | None):
        """프로필이 정한 메모·참고 자료를 기본값으로 채운다."""
        memory, chosen = profile_files(entry.profile if entry else None, base_memory, base_refs)
        state["memories"] = [""] + memory_options(memory_dir, memory)
        memory_box["values"] = [NO_MEMORY] + [Path(m).name if Path(m).parent == Path(memory_dir) else m
                                              for m in state["memories"][1:]]
        memory_box.current(state["memories"].index(memory) if memory in state["memories"] else 0)
        state["refs"] = ref_options(refs_dir, chosen)
        ref_list.delete(0, "end")
        for i, r in enumerate(state["refs"]):
            ref_list.insert("end", Path(r).name if Path(r).parent == Path(refs_dir) else r)
            if r in chosen:
                ref_list.selection_set(i)
        if not state["refs"]:
            ref_list.insert("end", f"(참고 자료를 쓰려면 {refs_dir}/ 폴더에 파일을 넣으세요)")

    def show(_event=None):
        entry = selected()
        detail.configure(state="normal")
        detail.delete("1.0", "end")
        detail.insert("1.0", describe(entry) if entry else "")
        detail.configure(state="disabled")
        fill_files(entry)

    def refresh(keep: str = ""):
        keep = keep or (selected().key if selected() else current_profile or NO_PROFILE)
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

    def start(_event=None):
        entry = selected()
        if entry is None:
            return
        if entry.error:
            messagebox.showerror("프로필 오류", entry.error)
            return
        text = goal_entry.get().strip()
        if not text:
            messagebox.showwarning("목표", "목표를 입력하세요.")
            goal_entry.focus_set()
            return
        chosen = [state["refs"][i] for i in ref_list.curselection() if i < len(state["refs"])]
        result["selection"] = Selection(entry.profile, state["memories"][memory_box.current()], chosen, text)
        root.destroy()

    def edit():
        entry = selected()
        if entry is None or entry.key == NO_PROFILE:
            messagebox.showinfo("프로필 파일", "프로필을 먼저 고르세요.")
            return
        open_file(folder / f"{entry.key}.toml")

    ttk.Button(buttons, text="프로필 파일 열기", command=edit).pack(side="left")
    ttk.Button(buttons, text="새로고침", command=refresh).pack(side="left", padx=(6, 0))
    ttk.Button(buttons, text="취소", command=root.destroy).pack(side="left", padx=(6, 0))
    ttk.Button(buttons, text="시작", command=start).pack(side="left", padx=(6, 0))

    listbox.bind("<<ListboxSelect>>", show)
    goal_entry.bind("<Return>", start)
    root.bind("<Escape>", lambda _e: root.destroy())

    refresh()
    goal_entry.focus_set()
    root.mainloop()
    return result["selection"]
