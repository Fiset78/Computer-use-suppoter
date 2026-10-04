"""말 끝 감지: 합성 소리로 끝/무음/최대 길이 판정을 검사."""
import numpy as np

from voice.endpoint import END, MAX, NO_SPEECH, EndpointDetector

SR = 16000
CHUNK = SR // 20  # 50ms


def run(detector, segments):
    """segments: [(초, 크기)] 순서대로 넣고, 처음 나온 판정과 그때의 시각(초)을 돌려준다."""
    rng = np.random.default_rng(0)
    for seconds, amp in segments:
        for _ in range(int(seconds * SR / CHUNK)):
            ev = detector.feed(rng.normal(0, amp, CHUNK).astype(np.float32))
            if ev:
                return ev, detector.elapsed / SR
    return None, detector.elapsed / SR


def test_end_after_speech_then_silence():
    ev, t = run(EndpointDetector(SR), [(0.5, 0.002), (2.0, 0.1), (3.0, 0.002)])
    assert ev == END and 3.6 <= t <= 3.9  # 말 끝(2.5초) + 1.2초 무렵


def test_short_pause_inside_sentence_does_not_end():
    ev, _ = run(EndpointDetector(SR), [(0.5, 0.002), (1.0, 0.1), (0.6, 0.002), (1.0, 0.1)])
    assert ev is None


def test_no_speech_times_out():
    ev, t = run(EndpointDetector(SR, no_speech_sec=3.0), [(5.0, 0.002)])
    assert ev == NO_SPEECH and abs(t - 3.0) < 0.1


def test_speaking_immediately_is_still_detected():
    # 측정 구간부터 말해도 기준값이 상한에 걸려 말로 인식된다
    ev, _ = run(EndpointDetector(SR), [(2.0, 0.1), (2.0, 0.002)])
    assert ev == END


def test_noisy_room_raises_threshold():
    d = EndpointDetector(SR)
    ev, _ = run(d, [(0.5, 0.008), (2.0, 0.008)])  # 소음만 계속: 말로 치지 않음
    assert d.threshold > 0.02 and not d.speech_started and ev is None


def test_max_length():
    ev, t = run(EndpointDetector(SR, max_sec=2.0), [(0.5, 0.002), (5.0, 0.1)])
    assert ev == MAX and abs(t - 2.0) < 0.1
