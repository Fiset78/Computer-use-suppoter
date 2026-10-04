"""음성 인식 결과 정리 (순수 함수)."""
import re
from pathlib import Path

import numpy as np

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
    if PROMPT_HEAD in text:  # 소리가 거의 없으면 앞 문맥(단어 힌트)을 그대로 받아쓰는 경우가 있다
        return ""
    for h in _HALLUCINATIONS:
        if h in text and len(text) <= len(h) + 5:
            return ""
    return text


def is_too_short(num_samples: int, sample_rate: int = SAMPLE_RATE) -> bool:
    return num_samples < sample_rate * MIN_SECONDS


# 명령에 자주 나오는 말. Whisper에 앞 문맥(initial_prompt)으로 주면 비슷한 발음을 이 단어로 맞춰 듣는다.
BASE_WORDS = (
    "메모장", "계산기", "파일 탐색기", "문서 폴더", "바탕화면", "설정", "작업 관리자", "그림판", "크롬", "엣지",
    "유튜브", "네이버", "구글", "카카오톡", "마인크래프트", "엑셀", "워드", "파워포인트",
)
PROMPT_HEAD = "컴퓨터에게 내리는 명령입니다."
PROMPT_EXAMPLES = "예: 메모장 열어줘. 크롬에서 유튜브 검색해줘. 안녕하세요라고 입력해줘. 저장하고 창 닫아줘."
WORDS_FILE = Path(__file__).resolve().parent.parent / "voice_words.txt"
MAX_PROMPT_CHARS = 400  # 너무 길면 앞 문맥이 오히려 인식을 흐린다


def load_extra_words(path: Path = WORDS_FILE) -> list[str]:
    """voice_words.txt의 단어 (한 줄에 하나 또는 쉼표 구분, #은 주석). 파일이 없으면 빈 목록."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return []
    words = []
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        words += [w.strip() for w in line.split(",") if w.strip()]
    return words


def build_prompt(extra_words: list[str]) -> str:
    """앞 문맥 = 안내 + 예시 명령 + 자주 쓰는 말(기본 단어 + 사용자 단어, 중복 없이)."""
    words = ", ".join(dict.fromkeys([*BASE_WORDS, *extra_words]))
    return f"{PROMPT_HEAD} {PROMPT_EXAMPLES} 자주 쓰는 말: {words}."[:MAX_PROMPT_CHARS]


def normalize_volume(audio, target_peak: float = 0.9, quiet_peak: float = 0.5, floor: float = 0.005):
    """작게 녹음된 소리를 키운다. 이미 충분히 크거나 사실상 무음이면 그대로 둔다."""
    audio = np.asarray(audio, dtype=np.float32)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak < floor or peak >= quiet_peak:
        return audio
    return audio * (target_peak / peak)
