"""실행 창 (터미널 없이 쓰기).

목표를 입력하거나 말로 하면 에이전트를 실행한다. 바탕화면 바로가기로 켠다 (install_shortcut.ps1).
    uv run app.py              # 터미널에서 켜기 (확인용)
    uv run app.py --minimized  # 최소화한 채로 켜기 (로그인 때 자동 실행에 쓰임)

- 실행 중에는 창을 최소화하고, 끝나도 다시 띄우지 않는다. 창이 화면을 가리면 Claude가 그 창을 보거나
  잘못 클릭할 수 있기 때문이다. 창이 최소화돼 있으면 상태는 화면 구석 알림으로 보여 준다 (실행 중에는 숨김).
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
from agent import sdk_loop, usage  # noqa: E402
from agent.hidden import hide_child_consoles  # noqa: E402
from logs.recorder import Recorder  # noqa: E402
from perception.capture import Screen  # noqa: E402
from safety.guard import Guard  # noqa: E402
from voice import tts  # noqa: E402
from voice.endpoint import MAX, NO_SPEECH  # noqa: E402
from voice.hotkey import GlobalHotkey  # noqa: E402
from voice.stt import MicRecorder, Transcriber  # noqa: E402

FONT = ("Malgun Gothic", 11)
# 창에서 고르는 생각 깊이 (보이는 이름 → PC_AGENT_EFFORT 값). 빠를수록 어려운 작업에서 실수가 늘 수 있다
EFFORTS = {"생각: 빠르게": "low", "생각: 보통": "medium", "생각: 깊게": "high"}
MINIMIZE_WAIT = 0.8  # 창이 내려가는 애니메이션이 끝날 때까지 기다린 뒤 첫 스크린샷을 찍는다
USAGE_REFRESH_MS = 10 * 60 * 1000  # 실행하지 않을 때 구독 한도를 다시 받아 오는 간격
AUTO_RUN_DELAY = 2   # 알아들은 뒤 자동 실행까지 기다리는 초 (그사이 Esc/단축키로 취소)


def hotkey_label(text: str) -> str:
    return "+".join(p.strip().capitalize() for p in text.split("+"))


def beep(kind: str) -> None:
    """녹음 시작/끝 알림음 (창을 보지 않고 단축키로 쓸 때 필요). Windows가 아니면 무시."""
    if sys.platform != "win32":
        return
    import winsound
    try:
        if kind == "start":
            # 녹음을 켜기 전에 끝까지 울린다. 알림음이 녹음돼 말소리로 잡히지 않게 하려는 것
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_NODEFAULT)
        else:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except RuntimeError:
        pass


class Overlay:
    """창이 최소화돼 있을 때 화면 오른쪽 아래에 잠깐 띄우는 작은 알림.
    에이전트가 실행 중일 때는 띄우지 않는다 (스크린샷에 찍히거나 클릭될 수 있으므로)."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.top: tk.Toplevel | None = None
        self.label: tk.Label | None = None
        self.job = None

    def _build(self) -> None:
        self.top = tk.Toplevel(self.root)
        self.top.overrideredirect(True)          # 제목 표시줄 없음
        self.top.attributes("-topmost", True)
        try:
            self.top.attributes("-alpha", 0.93)
        except tk.TclError:
            pass
        self.label = tk.Label(self.top, font=FONT, fg="#f2f5f7", bg="#1f2a33", justify="left",
                              wraplength=460, padx=16, pady=10)
        self.label.pack()
        self.top.withdraw()

    def show(self, text: str, seconds: float | None = None) -> None:
        if self.top is None:
            self._build()
        if self.job is not None:
            self.root.after_cancel(self.job)
            self.job = None
        self.label.configure(text=text)
        self.top.update_idletasks()
        w, h = self.top.winfo_reqwidth(), self.top.winfo_reqheight()
        x = self.top.winfo_screenwidth() - w - 24
        y = self.top.winfo_screenheight() - h - 80   # 작업 표시줄 위
        self.top.geometry(f"+{x}+{y}")
        self.top.deiconify()
        self.top.lift()
        if seconds:
            self.job = self.root.after(int(seconds * 1000), self.hide)

    def hide(self) -> None:
        if self.job is not None:
            self.root.after_cancel(self.job)
            self.job = None
        if self.top is not None:
            self.top.withdraw()

    @property
    def visible(self) -> bool:
        return self.top is not None and self.top.state() == "normal"


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
        root.geometry("680x600")
        root.minsize(480, 340)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(7, weight=1)

        row = ttk.Frame(frame)
        row.grid(row=0, column=0, sticky="ew")
        row.columnconfigure(0, weight=1)
        self.goal = tk.StringVar()
        self.entry = ttk.Entry(row, textvariable=self.goal, font=FONT)
        self.entry.grid(row=0, column=0, sticky="ew", ipady=4)
        self.entry.bind("<Return>", lambda e: self.run())
        self.entry.bind("<Key>", self._on_entry_key)
        root.bind("<Escape>", lambda e: self.cancel_countdown("취소했습니다."))
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
        self.speak = tk.BooleanVar(value=False)  # 결과 읽어 주기는 기본 꺼짐
        self.auto_stop = tk.BooleanVar(value=True)
        self.auto_run = tk.BooleanVar(value=True)
        row4 = ttk.Frame(frame)
        row4.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        default_effort = next((k for k, v in EFFORTS.items() if v == config.EFFORT), "생각: 보통")
        self.effort = tk.StringVar(value=default_effort)
        effort_menu = ttk.OptionMenu(row3, self.effort, default_effort, *EFFORTS)
        self.options = [
            effort_menu,
            ttk.Checkbutton(row3, text="웹 검색", variable=self.web),
            ttk.Checkbutton(row3, text="보조 도구", variable=self.assist),
            ttk.Checkbutton(row3, text="결과 읽어 주기", variable=self.speak),
            ttk.Checkbutton(row4, text="말이 끝나면 자동으로 멈추기", variable=self.auto_stop),
            ttk.Checkbutton(row4, text=f"알아들으면 {AUTO_RUN_DELAY}초 뒤 자동 실행", variable=self.auto_run),
        ]
        for cb in self.options:
            cb.pack(side="left", padx=(0, 14))
        self.countdown_job = None
        self.overlay = Overlay(root)

        self.status = tk.StringVar(value="목표를 입력하거나 '말하기'를 누르세요.")
        ttk.Label(frame, textvariable=self.status, font=FONT).grid(row=4, column=0, sticky="w", pady=(10, 4))
        self.hint = tk.StringVar(value="긴급 정지: 마우스를 화면 왼쪽 위 모서리로 빠르게 옮기기")
        ttk.Label(frame, textvariable=self.hint, foreground="#777").grid(row=5, column=0, sticky="w")

        # 구독 남은 사용량 바 (Claude Code가 실행 중에 알려 준 마지막 값)
        self.usage_box = ttk.LabelFrame(frame, text="남은 사용량 (구독)", padding=(10, 4))
        self.usage_box.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        self.usage_box.columnconfigure(1, weight=1)
        self.usage_rows: dict[str, tuple] = {}
        self.usage_empty = ttk.Label(self.usage_box, foreground="#777",
                                     text="아직 정보 없음 · 한 번 실행하면 Claude Code가 알려 줍니다")
        self.usage_empty.grid(row=0, column=0, columnspan=3, sticky="w")
        self.usage_checked = ttk.Label(self.usage_box, foreground="#777")
        self.usage_refreshing = False
        self.usage_btn = ttk.Button(self.usage_box, text="새로고침", command=self.refresh_usage, width=8)
        self.usage_btn.grid(row=0, column=3, sticky="ne", padx=(8, 0))
        self.usage_store = usage.load(sdk_loop.usage_file())
        self.show_usage(self.usage_store)
        sdk_loop.usage_listeners.append(lambda store: self.root.after(0, self.show_usage, store))
        self.root.after(1500, self.refresh_usage)  # 켜자마자 최신 한도를 받아 온다

        self.log = scrolledtext.ScrolledText(frame, height=10, font=("Malgun Gothic", 10), state="disabled")
        self.log.grid(row=7, column=0, sticky="nsew", pady=(8, 0))

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
        if self.countdown_job is not None:
            self.cancel_countdown("취소했습니다. 고치거나 다시 말하세요.")
            return
        self.toggle_mic()  # 창은 그대로 둔다 (최소화돼 있으면 알림으로 상태를 보여 줌)

    def notify(self, text: str, seconds: float | None = None) -> None:
        """창의 상태 줄에 쓰고, 창이 최소화돼 있으면 화면 구석 알림으로도 보여 준다.
        에이전트 실행 중에는 알림을 띄우지 않는다."""
        self.status.set(text)
        if self.running:
            return
        if self.root.state() == "iconic":
            self.overlay.show(text, seconds)
        else:
            self.overlay.hide()

    # ---------- 남은 사용량 ----------
    def show_usage(self, store: dict) -> None:
        self.usage_store = store
        entries = usage.ordered(store)
        if not entries:
            return
        self.usage_empty.grid_remove()
        for i, entry in enumerate(entries):
            kind = entry["type"]
            if kind not in self.usage_rows:
                name = ttk.Label(self.usage_box, text=usage.label(kind), width=12)
                bar = ttk.Progressbar(self.usage_box, maximum=100, length=240)
                text = ttk.Label(self.usage_box)
                self.usage_rows[kind] = (name, bar, text)
            name, bar, text = self.usage_rows[kind]
            name.grid(row=i, column=0, sticky="w")
            bar.grid(row=i, column=1, sticky="ew", padx=8, pady=2)
            text.grid(row=i, column=2, sticky="w")
            rest = usage.remaining(entry)
            bar.configure(value=0 if rest is None else rest * 100)
            text.configure(text=usage.describe(entry))
        checked = max(e.get("checked_at") or 0 for e in entries)
        if checked:
            self.usage_checked.configure(text="마지막 확인 " + time.strftime("%m/%d %H:%M", time.localtime(checked)))
            self.usage_checked.grid(row=len(entries), column=0, columnspan=3, sticky="w")
        # 초기화 시각이 지나면 글자가 바뀌도록 1분마다 다시 그린다
        if getattr(self, "_usage_job", None) is None:
            def tick():
                self._usage_job = None
                self.show_usage(self.usage_store)
            self._usage_job = self.root.after(60_000, tick)

    def refresh_usage(self) -> None:
        """Claude Code에 구독 한도를 물어본다 (모델 호출 없음). 실행 중이면 실행이 알아서 갱신한다."""
        if getattr(self, "_usage_timer", None) is not None:
            self.root.after_cancel(self._usage_timer)
        self._usage_timer = self.root.after(USAGE_REFRESH_MS, self.refresh_usage)
        if self.running or self.usage_refreshing:
            return
        self.usage_refreshing = True
        self.usage_btn.configure(state="disabled", text="확인 중")

        def work():
            store = sdk_loop.refresh_usage()
            self.root.after(0, done, store)

        def done(store):
            self.usage_refreshing = False
            self.usage_btn.configure(state="normal", text="새로고침")
            if store is None and not self.usage_store:
                self.usage_empty.configure(text="한도 정보를 받지 못했습니다 · Claude 구독으로 로그인했는지 확인하세요")

        threading.Thread(target=work, daemon=True).start()

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
            self.cancel_countdown()
            beep("start")
            auto = self.auto_stop.get()
            try:
                self.mic.start(on_event=(lambda ev: self.root.after(0, self._on_endpoint, ev)) if auto else None)
            except Exception as err:
                self.notify(f"마이크를 열지 못했습니다: {err}", 6)
                return
            self.mic_btn.configure(text="■ 멈추기")
            self.notify("🎤 듣고 있습니다... 말을 마치면 자동으로 멈춥니다." if auto else
                        "🎤 듣고 있습니다... 다 말하면 단축키나 '멈추기'를 누르세요.")
            if not self.stt.loaded:
                # 말하는 동안 모델을 미리 불러온다 (처음에는 내려받느라 오래 걸림)
                threading.Thread(target=self._preload, daemon=True).start()
            return

        self.mic_btn.configure(text="🎤 말하기")
        audio = self.mic.stop()
        beep("stop")
        if audio is None:
            self.notify("녹음이 너무 짧습니다. 다시 말해 주세요.", 4)
            return
        self.mic_btn.configure(state="disabled")
        self.transcribing = True
        self.notify("알아듣는 중..." if self.stt.loaded else
                        "알아듣는 중... (처음에는 음성 인식 모델(약 1.6GB)을 내려받아서 몇 분 걸릴 수 있습니다)")
        threading.Thread(target=self._transcribe, args=(audio,), daemon=True).start()

    def _on_endpoint(self, event: str) -> None:
        """말 끝 감지 결과 (오디오 스레드 → 메인 스레드)."""
        if not self.mic.recording:
            return  # 그사이 사용자가 직접 멈췄다
        if event == NO_SPEECH:
            self.mic.stop()
            beep("stop")
            self.mic_btn.configure(text="🎤 말하기")
            self.notify("말소리가 들리지 않아 멈췄습니다. 마이크를 확인하고 다시 말해 주세요.", 5)
            return
        if event == MAX:
            print("녹음이 최대 길이에 닿아 멈췄습니다.")
        self.toggle_mic()  # 멈추고 알아듣기

    def _on_entry_key(self, event) -> None:
        # 자동 실행을 기다리는 동안 직접 고치기 시작하면 자동 실행을 멈춘다
        if self.countdown_job is not None and event.keysym not in ("Return", "Escape"):
            self.cancel_countdown("자동 실행을 멈췄습니다. 고친 뒤 Enter로 실행하세요.")

    def start_countdown(self, remaining: int) -> None:
        if remaining <= 0:
            self.countdown_job = None
            self.run()
            return
        self.notify(f"{remaining}초 뒤 실행합니다\n\"{self.goal.get()}\"\n취소: 단축키 또는 Esc")
        self.countdown_job = self.root.after(1000, self.start_countdown, remaining - 1)

    def cancel_countdown(self, message: str | None = None) -> None:
        if self.countdown_job is None:
            return
        self.root.after_cancel(self.countdown_job)
        self.countdown_job = None
        if message:
            self.notify(message, 4)

    def _preload(self) -> None:
        try:
            self.stt.load()
            print(f"음성 인식 모델 준비 완료: {self.stt.model_name}")
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
            self.notify(f"음성 인식 실패: {err}", 6)
            return
        if not text:
            self.notify("알아듣지 못했습니다. 다시 말해 주세요.", 4)
            return
        print(f"🎤 알아들은 말: {text}")
        self.goal.set(text)
        self.entry.icursor("end")
        if self.auto_run.get():
            self.start_countdown(AUTO_RUN_DELAY)
            return
        self.notify(f"이렇게 알아들었습니다: \"{text}\"\n맞으면 창에서 실행(Enter)을 누르세요.", 8)

    # ---------- 실행 ----------
    def set_running(self, running: bool) -> None:
        self.running = running
        state = "disabled" if running else "normal"
        for w in (self.run_btn, self.mic_btn, self.entry, *self.options):
            w.configure(state=state)
        self.stop_btn.configure(state="normal" if running else "disabled")

    def run(self) -> None:
        self.cancel_countdown()
        goal = self.goal.get().strip()
        if self.running or self.mic.recording:
            return
        if not goal:
            self.status.set("목표가 비어 있습니다.")
            return
        config.WEB = self.web.get()
        config.EFFORT = EFFORTS[self.effort.get()]
        config.ASSIST = list(config.ASSIST_GROUPS) if self.assist.get() else []
        self.stop_event.clear()
        self.set_running(True)
        self.overlay.hide()
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
            print(f"엔진 {config.ENGINE} · 생각 {config.EFFORT} · 웹 검색 {'켬' if config.WEB else '끔'} · "
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
        brief = spoken if len(spoken) <= 160 else spoken[:160] + "…"
        self.notify(f"{summary}\n{brief}".strip(), 10)
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
            # 메인 창은 최소화한 채로 두고, 보이지 않는 작은 창을 부모로 대화상자만 맨 앞에 띄운다
            holder = tk.Toplevel(self.root)
            holder.overrideredirect(True)
            holder.attributes("-topmost", True)
            holder.geometry("1x1+{}+{}".format(self.root.winfo_screenwidth() // 2,
                                               self.root.winfo_screenheight() // 3))
            try:
                answer["yes"] = messagebox.askyesno(
                    "위험할 수 있는 행동", f"{what}\n\n실행할까요?", icon="warning", parent=holder)
            finally:
                holder.destroy()
                done.set()

        self.root.after(0, show)
        done.wait()
        time.sleep(0.3)  # 대화상자가 사라진 뒤에 행동한다
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
    hide_child_consoles()  # 실행할 때 Claude Code의 검은 콘솔 창이 뜨지 않게
    root = tk.Tk()
    App(root)
    if "--minimized" in sys.argv[1:]:
        # Windows 로그인 때 자동 실행: 최소화한 채로 단축키만 기다린다
        root.iconify()
    root.mainloop()


if __name__ == "__main__":
    main()
