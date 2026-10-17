"""시작 창: 목록, 상세 보기, 메모·참고 자료 기본값, main 연결 (tkinter 없이)."""
from pathlib import Path

import pytest

import config
import main
from agent import gui, profiles

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg(monkeypatch):
    for attr in ("MODEL", "MAX_STEPS", "WINDOW", "INPUT_BACKEND", "ASSIST", "MEMORY_FILE", "REFS", "MODE",
                 "PROFILE_NAME", "PROFILE_PROMPT", "ACTION_DELAY"):
        monkeypatch.setattr(config, attr, getattr(config, attr))
    return config


def test_entries_lists_real_profiles():
    found = {e.key: e for e in gui.entries(ROOT / "profiles")}
    assert list(found)[0] == gui.NO_PROFILE
    assert {"desktop", "minecraft", "babaisyou"} <= set(found)
    assert found["babaisyou"].label == "Baba Is You [게임 조작]"
    assert not any(e.error for e in found.values())


def test_entries_keeps_broken_profile_with_error(tmp_path):
    (tmp_path / "ok.toml").write_text('name = "좋음"\nmode = "desktop"\n', encoding="utf-8")
    (tmp_path / "bad.toml").write_text('mode = "game"\nwindw = "오타"\n', encoding="utf-8")
    (tmp_path / "_template.toml").write_text('name = "숨김"\n', encoding="utf-8")
    got = gui.entries(tmp_path)
    assert [e.key for e in got] == ["none", "bad", "ok"]
    assert "windw" in got[1].error and got[1].label == "bad (오류)"
    assert "불러오지 못했습니다" in gui.describe(got[1])
    assert [e.key for e in gui.entries(tmp_path / "없음")] == ["none"]


def test_describe_shows_settings_and_game_defaults(tmp_path):
    p = tmp_path / "g.toml"
    p.write_text('name = "게임"\nmode = "game"\nwindow = "Game"\nprompt = """\n' +
                 "\n".join(f"줄{i}" for i in range(20)) + '\n"""\n', encoding="utf-8")
    text = gui.describe(gui.Entry("g", "게임", profiles.load(p)))
    assert "모드: 게임 조작" in text and "창 제목: Game" in text
    assert "입력 백엔드: directinput" in text and "보조 도구: game" in text   # game 모드 기본값
    assert "줄0" in text and "줄19" not in text and "8줄 더" in text
    baba = profiles.load(ROOT / "profiles" / "babaisyou.toml")
    assert "보조 도구: 없음" in gui.describe(gui.Entry("babaisyou", "", baba))
    assert "프로필 없이" in gui.describe(gui.Entry("none", ""))


def test_profile_files_use_profile_then_base():
    baba = profiles.load(ROOT / "profiles" / "babaisyou.toml")
    assert gui.profile_files(baba, "memory/env.md", ["refs/a.md"]) == ("memory/babaisyou.md", ["refs/a.md"])
    assert gui.profile_files(None, "memory/env.md", ("refs/a.md",)) == ("memory/env.md", ["refs/a.md"])


def test_options_include_profile_files_not_on_disk(tmp_path):
    (tmp_path / "mem").mkdir()
    (tmp_path / "mem" / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "refs").mkdir()
    (tmp_path / "refs" / "b.png").write_bytes(b"x")
    mem = gui.memory_options(tmp_path / "mem", "memory/new.md")
    assert [Path(m).name for m in mem] == ["a.md", "new.md"]
    assert gui.memory_options(tmp_path / "mem", str(tmp_path / "mem" / "a.md")) == [str(tmp_path / "mem" / "a.md")]
    got = gui.ref_options(tmp_path / "refs", ["refs/sub/c.md"])
    assert [Path(r).name for r in got] == ["b.png", "c.md"]


def test_use_window_only_without_goal_and_choices():
    assert main.use_window(main.parse_args([]), "")
    assert not main.use_window(main.parse_args(["목표"]), "목표")
    assert main.use_window(main.parse_args(["--gui", "목표"]), "목표")
    for argv in (["--no-gui"], ["--no-pick"], ["--profile", "desktop"], ["--memory", "none"], ["--ref", "a.md"]):
        assert not main.use_window(main.parse_args(argv), "")


def test_choose_in_window_applies_selection(cfg, monkeypatch):
    baba = profiles.load(ROOT / "profiles" / "babaisyou.toml")
    monkeypatch.setattr(gui, "choose", lambda *a, **k: gui.Selection(baba, "", ["refs/x.md"], "레벨 깨기"))
    sel = main.choose_in_window("")
    assert sel.goal == "레벨 깨기"
    assert config.MODE == "game" and config.WINDOW == "Baba Is You"
    assert config.MEMORY_FILE == "" and config.REFS == ["refs/x.md"]   # 창에서 고른 값이 프로필보다 우선


def test_choose_in_window_cancel_and_fallback(cfg, monkeypatch):
    monkeypatch.setattr(gui, "choose", lambda *a, **k: None)
    assert main.choose_in_window("") is None

    def broken(*a, **k):
        raise ImportError("No module named 'tkinter'")
    monkeypatch.setattr(gui, "choose", broken)
    assert main.choose_in_window("") is False
