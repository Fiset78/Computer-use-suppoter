"""마이크 녹음과 음성 인식 (faster-whisper, 내 PC에서 실행. 인터넷/비용 없음).

- MicRecorder: start()로 녹음을 시작하고 stop()으로 멈춰 소리 데이터를 받는다.
- Transcriber: 처음 쓸 때 모델을 불러온다 (첫 실행에서 모델을 내려받음).
무거운 의존성(sounddevice, faster_whisper)은 실제로 쓸 때만 import한다.
"""
import os
import threading

from voice.text import SAMPLE_RATE, clean_transcript, is_too_short

# 모델 크기: tiny < base < small < medium < large-v3. 클수록 정확하지만 느리다.
# small은 한국어가 쓸 만하고 CPU에서도 짧은 명령은 몇 초 안에 끝난다.
MODEL_NAME = os.getenv("PC_AGENT_WHISPER_MODEL", "small")


class MicRecorder:
    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self._chunks = []
        self._stream = None

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        import sounddevice as sd

        self._chunks = []

        def callback(indata, frames, time_info, status):
            self._chunks.append(indata.copy())

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
                from faster_whisper import WhisperModel
                self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")

    def transcribe(self, audio) -> str:
        self.load()
        segments, _ = self._model.transcribe(audio, language=self.language, vad_filter=True, beam_size=5)
        return clean_transcript([s.text for s in segments])
