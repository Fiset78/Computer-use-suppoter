"""말 끝 감지 (순수 로직). 녹음 중 들어오는 소리 조각을 받아 언제 멈출지 정한다.

- 처음 calib_sec 동안의 소리 크기(하위 20%)로 주변 소음 수준을 잰다.
  곧바로 말을 시작해도 소음으로 잘못 재지 않도록 기준값은 max_threshold를 넘지 않는다
- 소음보다 ratio배 이상 큰 소리가 나면 말이 시작된 것으로 본다 (측정 구간 자체는 말로 치지 않음)
- 말이 시작된 뒤 silence_sec 동안 조용하면 "end"
- no_speech_sec이 지나도록 말이 없으면 "no_speech", max_sec을 넘으면 "max"
"""
import numpy as np

END, NO_SPEECH, MAX = "end", "no_speech", "max"


class EndpointDetector:
    def __init__(self, sample_rate: int, silence_sec: float = 2.0, calib_sec: float = 0.3,
                 min_threshold: float = 0.01, max_threshold: float = 0.04, ratio: float = 3.0,
                 no_speech_sec: float = 8.0, max_sec: float = 30.0):
        self.sample_rate = sample_rate
        self.silence_sec = silence_sec
        self.calib_sec = calib_sec
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self.ratio = ratio
        self.no_speech_sec = no_speech_sec
        self.max_sec = max_sec
        self.elapsed = 0          # 지금까지 받은 표본 수
        self.quiet = 0            # 마지막으로 큰 소리가 난 뒤 지난 표본 수
        self.speech_started = False
        self._calib: list[float] = []
        self.threshold: float | None = None

    def feed(self, chunk) -> str | None:
        """소리 조각 하나를 받아, 멈출 때가 되면 END/NO_SPEECH/MAX를 돌려준다."""
        chunk = np.asarray(chunk, dtype=np.float32).reshape(-1)
        n = len(chunk)
        if n == 0:
            return None
        rms = float(np.sqrt(np.mean(chunk * chunk)))
        self.elapsed += n
        seconds = self.elapsed / self.sample_rate

        if self.threshold is None:
            self._calib.append(rms)
            if seconds < self.calib_sec:
                return None
            noise = float(np.percentile(self._calib, 20))
            self.threshold = min(self.max_threshold, max(self.min_threshold, noise * self.ratio))
            return None

        if rms > self.threshold:
            self.speech_started = True
            self.quiet = 0
        else:
            self.quiet += n

        if seconds >= self.max_sec:
            return MAX
        if self.speech_started and self.quiet / self.sample_rate >= self.silence_sec:
            return END
        if not self.speech_started and seconds >= self.no_speech_sec:
            return NO_SPEECH
        return None
