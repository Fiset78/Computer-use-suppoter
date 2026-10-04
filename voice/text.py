"""음성 인식 결과 정리 (순수 함수)."""
import re

SAMPLE_RATE = 16000       # Whisper가 받는 표본 주파수
MIN_SECONDS = 0.5         # 이보다 짧은 녹음은 실수로 누른 것으로 본다

# 무음이나 잡음에서 Whisper가 자주 지어내는 문장 (방송 자막 학습 흔적)
_HALLUCINATIONS = (
    "시청해 주셔서 감사합니다",
    "시청해주셔서 감사합니다",
    "구독과 좋아요",
    "MBC 뉴스",
)


def clean_transcript(segments: list[str]) -> str:
    """구간별 텍스트를 한 문장으로 합치고, 공백과 지어낸 문장을 정리한다."""
    text = " ".join(s.strip() for s in segments if s and s.strip())
    text = re.sub(r"\s+", " ", text).strip()
    for h in _HALLUCINATIONS:
        if h in text and len(text) <= len(h) + 5:
            return ""
    return text


def is_too_short(num_samples: int, sample_rate: int = SAMPLE_RATE) -> bool:
    return num_samples < sample_rate * MIN_SECONDS
