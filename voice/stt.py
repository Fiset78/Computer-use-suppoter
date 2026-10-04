"""마이크 녹음과 음성 인식 (faster-whisper, 내 PC에서 실행. 인터넷/비용 없음).

- MicRecorder: start()로 녹음을 시작하고 stop()으로 멈춰 소리 데이터를 받는다.
- Transcriber: 처음 쓸 때 모델을 불러온다 (첫 실행에서 모델을 내려받음).
무거운 의존성(sounddevice, faster_whisper)은 실제로 쓸 때만 import한다.
"""
import os
import sys
import threading
import types

from voice.endpoint import EndpointDetector
from voice.text import SAMPLE_RATE, clean_transcript, is_too_short

# 모델 크기: tiny < base < small < medium < large-v3. 클수록 정확하지만 느리다.
# small은 한국어가 쓸 만하고 CPU에서도 짧은 명령은 몇 초 안에 끝난다.
MODEL_NAME = os.getenv("PC_AGENT_WHISPER_MODEL", "small")


BLOCKED_HINT = (
    "Windows 보안(스마트 앱 컨트롤 등)이 음성 인식 라이브러리 파일을 막았습니다. "
    "Windows 보안 → 앱 및 브라우저 컨트롤 → 스마트 앱 컨트롤 설정을 확인하세요."
)


def import_whisper_model():
    """faster_whisper.WhisperModel을 불러온다.

    faster-whisper는 오디오 '파일'을 풀 때만 PyAV(av)를 쓴다. 우리는 녹음한 numpy 배열을 바로 넘기므로
    av가 없어도 된다. Windows 스마트 앱 컨트롤이 av의 DLL(_core)을 막는 경우가 있어서,
    av를 불러오지 못하면 빈 모듈로 대신하고 계속 진행한다.
    """
    try:
        import av  # noqa: F401
    except (ImportError, OSError):
        for name in [m for m in sys.modules if m == "av" or m.startswith("av.")]:
            del sys.modules[name]
        sys.modules["av"] = types.ModuleType("av")
    try:
        from faster_whisper import WhisperModel
    except (ImportError, OSError) as err:
        raise RuntimeError(f"{BLOCKED_HINT} (원인: {err})") from err
    return WhisperModel


class MicRecorder:
    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self._chunks = []
        self._stream = None

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self, on_event=None) -> None:
        """녹음을 시작한다. on_event를 주면 말 끝을 감지해 "end"/"no_speech"/"max"로 한 번 알려 준다.
        on_event는 오디오 스레드에서 불리므로 가볍게 처리해야 한다 (창에 넘기기만 할 것)."""
        import sounddevice as sd

        self._chunks = []
        detector = EndpointDetector(self.sample_rate) if on_event is not None else None
        signaled = False

        def callback(indata, frames, time_info, status):
            nonlocal signaled
            self._chunks.append(indata.copy())
            if detector is not None and not signaled:
                event = detector.feed(indata[:, 0])
                if event:
                    signaled = True
                    on_event(event)

        self._stream = sd.InputStream(samplerate=self.sample_rate, channels=1, dtype="float32",
                                      callback=callback)
        self._stream.start()

    def stop(self):
        """녹음을 멈추고 1차원 float32 배열을 돌려준다. 너무 짧으면 None."""
        import numpy as np

        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        if not self._chunks:
            return None
        audio = np.concatenate(self._chunks)[:, 0]
        self._chunks = []
        return None if is_too_short(len(audio), self.sample_rate) else audio


class Transcriber:
    def __init__(self, model_name: str = MODEL_NAME, language: str = "ko"):
        self.model_name = model_name
        self.language = language
        self._model = None
        self._lock = threading.Lock()  # 미리 불러오기와 인식이 겹쳐도 모델은 한 번만 불러온다

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        with self._lock:
            if self._model is None:
                WhisperModel = import_whisper_model()
                self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")

    def transcribe(self, audio) -> str:
        self.load()
        segments, _ = self._model.transcribe(audio, language=self.language, vad_filter=True, beam_size=5)
        return clean_transcript([s.text for s in segments])
