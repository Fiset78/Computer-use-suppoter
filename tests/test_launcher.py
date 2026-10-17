"""프로필 고르기 창: 목록, 상세 보기, 실행 명령 (tkinter 없이 순수 함수만)."""
from pathlib import Path

import pytest

import launcher
import main

ROOT = Path(__file__).resolve().parents[1]


def test_entries_lists_real_profiles():
    found = {e.key: e for e in launcher.entries(ROOT / "profiles")}
    assert list(found)[0] == launcher.NO_PROFILE
    assert {"desktop", "minecraft", "babaisyou"} <= set(found)
    assert found["babaisyou"].label == "Baba Is You [게임 조작]"
    assert not any(e.error for e in found.values())


def test_entries_keeps_broken_profile_with_error(tmp_path):
    (tmp_path / "ok.toml").write_text('name = "좋음"\nmode = "desktop"\n', encoding="utf-8")
    (tmp_path / "bad.toml").write_text('mode = "game"\nwindw = "오타"\n', encoding="utf-8")
    (tmp_path / "_template.toml").write_text('name = "숨김"\n', encoding="utf-8")
    got = launcher.entries(tmp_path)
    assert [e.key for e in got] == ["none", "bad", "ok"]
    assert "windw" in got[1].error and got[1].label == "bad (오류)"
    assert "불러오지 못했습니다" in launcher.describe(got[1])


def test_entries_missing_folder(tmp_path):
    assert [e.key for e in launcher.entries(tmp_path / "없음")] == ["none"]


def test_describe_shows_settings_and_game_defaults(tmp_path):
    p = tmp_path / "g.toml"
    p.write_text('name = "게임"\nmode = "game"\nwindow = "Game"\nprompt = """\n' +
                 "\n".join(f"줄{i}" for i in range(20)) + '\n"""\n', encoding="utf-8")
    text = launcher.describe(launcher.Entry("g", "게임", launcher.profiles.load(p)))
    assert "모드: 게임 조작" in text and "창 제목: Game" in text
    assert "입력 백엔드: directinput" in text and "보조 도구: game" in text   # game 모드 기본값
    assert "지식 메모: 없음" in text
    assert "줄0" in text and "줄19" not in text and "8줄 더" in text


def test_describe_empty_assist_and_no_profile():
    prof = launcher.profiles.load(ROOT / "profiles" / "babaisyou.toml")
    assert "보조 도구: 없음" in launcher.describe(launcher.Entry("babaisyou", "", prof))
    assert "프로필 없이" in launcher.describe(launcher.Entry("none", ""))


def test_build_command_passes_goal_after_separator():
    cmd = launcher.build_command("babaisyou", "  -레벨 깨기  ", python="py")
    assert cmd[0] == "py" and cmd[2] == "--child"
    args = main.parse_args(cmd[3:])
    assert args.profile == "babaisyou" and args.no_pick
    assert " ".join(args.goal) == "-레벨 깨기"


def test_build_command_rejects_empty_goal():
    with pytest.raises(ValueError):
        launcher.build_command("desktop", "   ")
