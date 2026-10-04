"""결과 읽어 주기. Windows 내장 음성 합성(System.Speech)을 PowerShell로 부른다. 추가 설치 없음.
한국어 음성은 Windows에 한국어가 설치돼 있으면 기본으로 들어 있다."""
import os
import subprocess
import sys
import threading

_SCRIPT = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$ko = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ko-KR' } | Select-Object -First 1; "
    "if ($ko) { $s.SelectVoice($ko.VoiceInfo.Name) }; "
    "$s.Speak($env:PC_AGENT_TTS_TEXT)"
)
MAX_CHARS = 400  # 긴 보고는 앞부분만 읽는다


def speak(text: str) -> None:
    """백그라운드에서 읽는다 (호출한 쪽을 막지 않음). Windows가 아니면 아무것도 하지 않는다."""
    text = (text or "").strip()[:MAX_CHARS]
    if not text or sys.platform != "win32":
        return

    def run():
        # 텍스트를 명령줄에 끼워 넣지 않고 환경 변수로 넘긴다 (따옴표·특수문자 안전)
        env = {**os.environ, "PC_AGENT_TTS_TEXT": text}
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", _SCRIPT], env=env,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=120)
        except Exception:
            pass  # 읽어 주기는 부가 기능이라 실패해도 무시한다

    threading.Thread(target=run, daemon=True).start()
