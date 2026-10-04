"""실행 창 (터미널 없이 쓰기).

목표를 입력하거나 말로 하면 에이전트를 실행한다. 바탕화면 바로가기로 켠다 (install_shortcut.ps1).
    uv run app.py              # 터미널에서 켜기 (확인용)

- 실행 중에는 창을 최소화한다. 창이 화면을 가리면 Claude가 그 창을 보거나 잘못 클릭할 수 있기 때문이다.
- 정지 버튼은 다음 행동 직전에 멈춘다. 긴급 정지(마우스를 왼쪽 위 모서리로)도 그대로 동작한다.
- 위험 행동 확인(y/n)은 대화상자로 묻는다.
- 전역 단축키(기본 Ctrl+Alt+Space, PC_AGENT_HOTKEY): 어느 창에서든 눌러 말하기 시작/멈추기,
  실행 중에 누르면 정지.
"""
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

# DPI 설정은 다른 GUI 모듈(tkinter, pyautogui)을 import 하기 전에 해야 한다
from perception.capture import enable_dpi_awareness

enable_dpi_awareness()

import tkinter as tk  # noqa: E402
from tkinter import messagebox, scrolledtext, ttk  # noqa: E402

import config  # noqa: E402
from actions import backends  # noqa: E402
from actions.executor import Executor  # noqa: E402
from agent.engine import get_runner  # noqa: E402
from logs.recorder import Recorder  # noqa: E402
from perception.capture import Screen  # noqa: E402
from safety.guard import Guard  # noqa: E402
from voice import tts  # noqa: E402
from voice.hotkey import GlobalHotkey  # noqa: E402
from voice.stt import MicRecorder, Transcriber  # noqa: E402

FONT = ("Malgun Gothic", 11)
MINIMIZE_WAIT = 0.8  # 창이 내려가는 애니메이션이 끝날 때까지 기다린 뒤 첫 스크린샷을 찍는다


def hotkey_label(text: str) -> str:
    return "+".join(p.strip().capitalize() for p in text.split("+"))


def beep(kind: str) -> None:
    """녹음 시작/끝 알림음 (창을 보지 않고 단축키로 쓸 때 필요). Windows가 아니면 무시."""
    if sys.platform != "win32":
        return
    import winsound
    try:
        winsound.MessageBeep(winsound.MB_OK if kind == "start" else winsound.MB_ICONASTERISK)
    except RuntimeError:
        pass


class QueueWriter:
    """print 출력을 창의 기록 칸으로 보낸다 (pythonw에는 콘솔이 없어서 stdout이 None이다)."""

    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, s: str) -> int:
        if s:
            self.q.put(s)
        return len(s)

    def flush(self) -> None:
        pass


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.log_q: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.running = False
        self.transcribing = False
        self.mic = MicRecorder()
        self.stt = Transcriber()

        root.title("pc-agent")
        root.geometry("640x500")
        root.minsize(480, 340)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)

        row = ttk.Frame(frame)
        row.grid(row=0, column=0, sticky="ew")
        row.columnconfigure(0, weight=1)
        self.goal = tk.StringVar()
        self.entry = ttk.Entry(row, textvariable=self.goal, font=FONT)
        self.entry.grid(row=0, column=0, sticky="ew", ipady=4)
        self.entry.bind("<Return>", lambda e: self.run())
        self.mic_btn = ttk.Button(row, text="🎤 말하기", command=self.toggle_mic, width=12)
        self.mic_btn.grid(row=0, column=1, padx=(8, 0))

        row2 = ttk.Frame(frame)
        row2.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.run_btn = ttk.Button(row2, text="실행", command=self.run)
        self.run_btn.pack(side="left")
        self.stop_btn = ttk.Button(row2, text="정지", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(6, 0))

        row3 = ttk.Frame(frame)
        row3.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.web = tk.BooleanVar(value=config.WEB)
        self.assist = tk.BooleanVar(value=bool(config.ASSIST))
        self.speak = tk.BooleanVar(value=True)
        self.auto_run = tk.BooleanVar(value=False)
        self.options = [
            ttk.Checkbutton(row3, text="웹 검색", variable=self.web),
            ttk.Checkbutton(row3, text="보조 도구", variable=self.assist),
            ttk.Checkbutton(row3, text="결과 읽어 주기", variable=self.speak),
            ttk.Checkbutton(row3, text="알아들으면 바로 실행", variable=self.auto_run),
        ]
        for cb in self.options:
            cb.pack(side="left", padx=(0, 14))

        self.status = tk.StringVar(value="목표를 입력하거나 '말하기'를 누르세요.")
        ttk.Label(frame, textvariable=self.status, font=FONT).grid(row=3, column=0, sticky="w", pady=(10, 4))
        self.hint = tk.StringVar(value="긴급 정지: 마우스를 화면 왼쪽 위 모서리로 빠르게 옮기기")
        ttk.Label(frame, textvariable=self.hint, foreground="#777").grid(row=4, column=0, sticky="w")

        self.log = scrolledtext.ScrolledText(frame, height=12, font=("Malgun Gothic", 10), state="disabled")
        self.log.grid(row=5, column=0, sticky="nsew", pady=(8, 0))

        sys.stdout = sys.stderr = QueueWriter(self.log_q)
        self.root.after(100, self.drain_log)
        self.entry.focus_set()
        self.hotkey = self._start_hotkey()

    # ---------- 전역 단축키 ----------
    def _start_hotkey(self):
        # 직접 정한 단축키는 그것만 쓴다. 기본값이면 다른 프로그램과 겹칠 때 다음 후보로 넘어간다
        candidates = [config.HOTKEY] + ([] if config.HOTKEY_FROM_ENV else list(config.HOTKEY_FALLBACKS))
        failed = []
        for text in candidates:
            try:
                hk = GlobalHotkey(text, lambda: self.root.after(0, self.on_hotkey))
            except ValueError as err:
                print(f"단축키 설정 오류 (PC_AGENT_HOTKEY={text}): {err}")
                continue
            if hk.start():
                label = hotkey_label(text)
                if failed:
                    print(f"{', '.join(map(hotkey_label, failed))}는 다른 프로그램이 쓰고 있어서 "
                          f"{label}로 등록했습니다.")
                self.hint.set(f"단축키 {label}: 말하기/멈추기 · 실행 중에는 정지 · "
                              "긴급 정지: 마우스를 왼쪽 위 모서리로")
                return hk
            if sys.platform != "win32":
                print(hk.error)
                return None
            failed.append(text)
        if failed:
            print(f"단축키를 등록하지 못했습니다 (시도: {', '.join(map(hotkey_label, failed))}).\n"
                  "실행 창이 이미 하나 켜져 있지 않은지 확인하세요. 다른 단축키를 쓰려면 "
                  "PowerShell에서 setx PC_AGENT_HOTKEY \"ctrl+shift+f10\" 후 창을 다시 켜세요.")
            self.hint.set("단축키 없음 (기록 칸 참고) · 긴급 정지: 마우스를 왼쪽 위 모서리로")
        return None

    def on_hotkey(self) -> None:
        if self.running:
            self.stop()
            return
        if not self.mic.recording:
            self.show()  # 무엇을 듣고 있는지 보이게 창을 앞으로
        self.toggle_mic()

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(200, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()
        self.entry.focus_set()

    # ---------- 기록 칸 ----------
    def drain_log(self) -> None:
        chunks = []
        try:
            while True:
                chunks.append(self.log_q.get_nowait())
        except queue.Empty:
            pass
        if chunks:
            self.log.configure(state="normal")
            self.log.insert("end", "".join(chunks))
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(100, self.drain_log)

    # ---------- 음성 입력 ----------
    def toggle_mic(self) -> None:
        if self.running or self.transcribing:
            return
        if not self.mic.recording:
            try:
                self.mic.start()
            except Exception as err:
                self.status.set(f"마이크를 열지 못했습니다: {err}")
                return
            beep("start")
            self.mic_btn.configure(text="■ 멈추기")
            self.status.set("듣고 있습니다... 다 말하면 '멈추기'를 누르세요.")
            if not self.stt.loaded:
                # 말하는 동안 모델을 미리 불러온다 (처음에는 내려받느라 오래 걸림)
                threading.Thread(target=self._preload, daemon=True).start()
            return

        self.mic_btn.configure(text="🎤 말하기")
        audio = self.mic.stop()
        beep("stop")
        if audio is None:
            self.status.set("녹음이 너무 짧습니다. 다시 말해 주세요.")
            return
        self.mic_btn.configure(state="disabled")
        self.transcribing = True
        self.status.set("알아듣는 중..." if self.stt.loaded else
                        "알아듣는 중... (처음에는 음성 인식 모델을 내려받아서 몇 분 걸릴 수 있습니다)")
        threading.Thread(target=self._transcribe, args=(audio,), daemon=True).start()

    def _preload(self) -> None:
        try:
            self.stt.load()
        except Exception as err:
            print(f"음성 인식 모델을 불러오지 못했습니다: {err}")

    def _transcribe(self, audio) -> None:
        try:
            text, err = self.stt.transcribe(audio), None
        except Exception as e:
            text, err = "", e
        self.root.after(0, self._on_transcribed, text, err)

    def _on_transcribed(self, text: str, err) -> None:
        self.transcribing = False
        self.mic_btn.configure(state="normal")
        if err is not None:
            self.status.set(f"음성 인식 실패: {err}")
            return
        if not text:
            self.status.set("알아듣지 못했습니다. 다시 말해 주세요.")
            return
        self.goal.set(text)
        self.entry.icursor("end")
        if self.auto_run.get():
            self.run()
            return
        self.status.set("이렇게 알아들었습니다. 맞으면 '실행'(Enter), 틀리면 고치거나 다시 말하세요.")

    # ---------- 실행 ----------
    def set_running(self, running: bool) -> None:
        self.running = running
        state = "disabled" if running else "normal"
        for w in (self.run_btn, self.mic_btn, self.entry, *self.options):
            w.configure(state=state)
        self.stop_btn.configure(state="normal" if running else "disabled")

    def run(self) -> None:
        goal = self.goal.get().strip()
        if self.running or self.mic.recording:
            return
        if not goal:
            self.status.set("목표가 비어 있습니다.")
            return
        config.WEB = self.web.get()
        config.ASSIST = list(config.ASSIST_GROUPS) if self.assist.get() else []
        self.stop_event.clear()
        self.set_running(True)
        self.status.set("실행 중... (창은 최소화됩니다)")
        print(f"\n===== 목표: {goal} =====")
        self.root.iconify()
        threading.Thread(target=self._worker, args=(goal,), daemon=True).start()

    def _worker(self, goal: str) -> None:
        time.sleep(MINIMIZE_WAIT)
        recorder = None
        summary, spoken = "", ""
        try:
            run_agent, _ = get_runner(config.ENGINE)
            backend = backends.create(config.INPUT_BACKEND)
            screen = Screen(config.MAX_LONG_EDGE, config.MONITOR_INDEX)
            recorder = Recorder(config.RUNS_DIR, goal)
            executor = Executor(screen, Guard(confirm=True, ask=self.ask), recorder, config.ACTION_DELAY,
                                backend, stop_check=self.stop_event.is_set)
            print(f"엔진 {config.ENGINE} · 웹 검색 {'켬' if config.WEB else '끔'} · "
                  f"보조 도구 {', '.join(config.ASSIST) or '없음'} · 기록 {recorder.dir}")
            try:
                result = run_agent(goal, executor, recorder)
                summary = f"완료 ({result.status}) · 단계 {result.steps} · 행동 {result.actions}"
                spoken = result.final
                print(f"\n=== 결과 ({result.status}) ===\n{result.final}\n{summary}")
            except Exception as err:
                if not backends.is_failsafe(err):
                    raise
                reason = "abort_button" if isinstance(err, backends.StopRequested) else "failsafe"
                recorder.event("abort", reason=reason)
                summary = "정지했습니다." if reason == "abort_button" else "긴급 정지되었습니다."
                print(f"\n{summary}")
        except Exception as err:
            traceback.print_exc()
            summary = f"오류로 멈췄습니다: {err}"
        finally:
            if recorder is not None:
                recorder.close()
        self.root.after(0, self._finish, summary, spoken)

    def _finish(self, summary: str, spoken: str) -> None:
        self.set_running(False)
        self.status.set(summary)
        self.root.deiconify()
        self.root.lift()
        if self.speak.get() and spoken:
            tts.speak(spoken)

    def stop(self) -> None:
        if self.running:
            self.stop_event.set()
            self.status.set("다음 행동 직전에 멈춥니다...")

    def ask(self, what: str) -> bool:
        """실행 스레드에서 부른다. 메인 스레드에 대화상자를 띄우고 답을 기다린다."""
        done = threading.Event()
        answer = {"yes": False}

        def show():
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            answer["yes"] = messagebox.askyesno(
                "위험할 수 있는 행동", f"{what}\n\n실행할까요?", icon="warning", parent=self.root)
            self.root.attributes("-topmost", False)
            self.root.iconify()
            done.set()

        self.root.after(0, show)
        done.wait()
        if answer["yes"]:
            time.sleep(MINIMIZE_WAIT)  # 창이 다시 내려간 뒤에 행동한다
        return answer["yes"]

    def on_close(self) -> None:
        if self.running and not messagebox.askyesno("pc-agent", "실행 중입니다. 멈추고 닫을까요?", parent=self.root):
            return
        self.stop_event.set()
        if self.mic.recording:
            self.mic.stop()
        if self.hotkey is not None:
            self.hotkey.stop()
        self.root.destroy()


def already_running() -> bool:
    """실행 창이 이미 켜져 있는지 (이름 있는 뮤텍스). 두 개가 켜지면 단축키가 겹쳐서 하나만 허용한다."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    already_exists = 183  # ERROR_ALREADY_EXISTS
    # 핸들은 프로세스가 끝날 때까지 쥐고 있어야 하므로 모듈 전역에 둔다
    globals()["_instance_mutex"] = kernel32.CreateMutexW(None, False, "Local\\pc-agent-app")
    return ctypes.get_last_error() == already_exists


def main() -> None:
    os.chdir(Path(__file__).resolve().parent)  # 바로가기로 켜도 runs/ 폴더가 프로젝트 안에 생기게
    if already_running():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("pc-agent", "실행 창이 이미 켜져 있습니다. 작업 표시줄에서 찾아 주세요.")
        root.destroy()
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
