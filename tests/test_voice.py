"""음성 입력 정리 규칙과, 실행 창의 정지 버튼 경로 (GUI 없이 검사)."""
import pytest

from actions import backends
from voice.text import SAMPLE_RATE, clean_transcript, is_too_short


def test_clean_joins_and_trims():
    assert clean_transcript([" 메모장을 열고 ", "", "  안녕이라고   입력해줘"]) == "메모장을 열고 안녕이라고 입력해줘"


def test_clean_drops_hallucination_on_silence():
    assert clean_transcript(["시청해 주셔서 감사합니다."]) == ""
    # 실제 명령 안에 들어 있으면 지우지 않는다
    long = "유튜브에서 시청해 주셔서 감사합니다라는 영상을 찾아서 재생해줘"
    assert clean_transcript([long]) == long


def test_too_short():
    assert is_too_short(SAMPLE_RATE // 4)
    assert not is_too_short(SAMPLE_RATE * 2)


def test_stop_request_is_treated_as_failsafe():
    assert backends.is_failsafe(backends.StopRequested())


def test_executor_stops_before_next_action():
    from actions.executor import Executor
    from safety.guard import Guard

    class Backend:
        def __getattr__(self, name):
            raise AssertionError("정지 후에는 입력을 보내면 안 됩니다")

    ex = Executor(screen=None, guard=Guard(confirm=False), backend=Backend(), stop_check=lambda: True)
    with pytest.raises(backends.StopRequested):
        ex.run("key", {"text": "a"})


def test_guard_uses_dialog_callback():
    from safety.guard import Guard

    asked = []
    g = Guard(confirm=True, ask=lambda what: asked.append(what) or False)
    with pytest.raises(PermissionError):
        g.check_key(["alt", "f4"])
    assert asked and "alt+f4" in asked[0]


def test_whisper_loads_without_pyav(monkeypatch):
    """스마트 앱 컨트롤이 PyAV DLL을 막아도 faster-whisper를 불러올 수 있어야 한다."""
    import sys

    from voice import stt

    for name in [m for m in sys.modules if m == "av" or m.startswith("av.") or m.startswith("faster_whisper")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "av", None)  # import av → ImportError (차단 흉내)
    WhisperModel = stt.import_whisper_model()
    assert WhisperModel.__name__ == "WhisperModel"


def test_parse_hotkey():
    from voice import hotkey as hk

    mods, vk = hk.parse_hotkey("ctrl+alt+space")
    assert mods == hk.MOD_CONTROL | hk.MOD_ALT | hk.MOD_NOREPEAT and vk == 0x20
    assert hk.parse_hotkey("Win+Shift+V") == (hk.MOD_WIN | hk.MOD_SHIFT | hk.MOD_NOREPEAT, ord("V"))
    assert hk.parse_hotkey("ctrl+f9")[1] == 0x78


@pytest.mark.parametrize("bad", ["", "space", "ctrl+", "hyper+a", "ctrl+nokey"])
def test_parse_hotkey_rejects(bad):
    from voice.hotkey import parse_hotkey

    with pytest.raises(ValueError):
        parse_hotkey(bad)


def test_extra_words_file(tmp_path):
    from voice.text import build_prompt, load_extra_words

    f = tmp_path / "w.txt"
    f.write_text("# 주석\n디스코드, 스팀\n노션  # 메모\n\n디스코드\n", encoding="utf-8")
    words = load_extra_words(f)
    assert words == ["디스코드", "스팀", "노션", "디스코드"]
    prompt = build_prompt(words)
    assert "메모장" in prompt and prompt.count("디스코드") == 1  # 기본 단어 + 중복 없이 추가
    assert load_extra_words(tmp_path / "없음.txt") == []


def test_prompt_length_capped():
    from voice.text import MAX_PROMPT_CHARS, build_prompt

    assert len(build_prompt([f"단어{i}" for i in range(500)])) <= MAX_PROMPT_CHARS


def test_normalize_volume():
    import numpy as np

    from voice.text import normalize_volume

    quiet = np.array([0.0, 0.1, -0.05], dtype=np.float32)
    assert abs(float(np.max(np.abs(normalize_volume(quiet)))) - 0.9) < 1e-6
    loud = np.array([0.0, 0.7], dtype=np.float32)
    assert np.array_equal(normalize_volume(loud), loud)        # 충분히 크면 그대로
    silent = np.array([0.0, 0.001], dtype=np.float32)
    assert np.array_equal(normalize_volume(silent), silent)    # 무음은 키우지 않음
