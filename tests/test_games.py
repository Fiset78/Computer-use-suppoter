"""게임 지식 파일: 이름 읽기, 자동 감지, 직접 지정, 배운 점 덧붙이기."""
from pathlib import Path

import pytest

from agent import games

MINECRAFT = "# 마인크래프트\n이름: 마인크래프트, minecraft\n\n## 기본 조작\n- w 앞으로\n\n## 배운 점\n"


@pytest.fixture
def games_dir(tmp_path):
    (tmp_path / "minecraft.md").write_text(MINECRAFT, encoding="utf-8")
    (tmp_path / "terraria.md").write_text("# 테라리아\n이름: 테라리아\n", encoding="utf-8")
    (tmp_path / "_template.md").write_text("# 견본\n이름: 게임 이름\n", encoding="utf-8")
    return tmp_path


def test_list_games_reads_names_and_skips_template(games_dir):
    found = games.list_games(games_dir)
    assert [g.id for g in found] == ["minecraft", "terraria"]
    assert found[0].title == "마인크래프트"
    assert found[0].names == ["minecraft", "마인크래프트"]  # id와 겹치는 이름은 한 번만


def test_list_games_missing_dir(tmp_path):
    assert games.list_games(tmp_path / "없음") == []


def test_parse_without_header_uses_id():
    g = games.parse("그냥 메모", "stardew", Path("stardew.md"))
    assert (g.title, g.names) == ("stardew", ["stardew"])


@pytest.mark.parametrize("goal,expected", [
    ("마인크래프트에서 나무를 캐줘", "minecraft"),       # 조사가 붙어도 찾는다
    ("Open Minecraft and build a house", "minecraft"),  # 대소문자 무시
    ("테라리아 첫날 준비", "terraria"),
    ("메모장을 열어줘", None),
])
def test_detect(games_dir, goal, expected):
    g = games.detect(goal, games.list_games(games_dir))
    assert (g.id if g else None) == expected


def test_detect_prefers_longest_name(tmp_path):
    (tmp_path / "a.md").write_text("# A\n이름: 크래프트\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n이름: 마인크래프트\n", encoding="utf-8")
    assert games.detect("마인크래프트 하자", games.list_games(tmp_path)).id == "b"


def test_resolve(games_dir):
    found = games.list_games(games_dir)
    assert games.resolve("", "마인크래프트 해줘", found).id == "minecraft"
    assert games.resolve("테라리아", "마인크래프트 해줘", found).id == "terraria"  # 직접 지정이 우선
    assert games.resolve("none", "마인크래프트 해줘", found) is None
    with pytest.raises(ValueError, match="minecraft, terraria"):
        games.resolve("zelda", "", found)


def test_load_and_prompt(games_dir):
    game, text = games.load("", "minecraft 해줘", games_dir)
    prompt = games.as_prompt(game, text)
    assert prompt.startswith("[게임 지식: 마인크래프트]") and "- w 앞으로" in prompt
    assert games.load("", "메모장", games_dir) == (None, "")


def test_add_note_appends_to_notes_section():
    text, added = games.add_note(MINECRAFT, "shift+클릭으로 바로 옮긴다", "2026-10-17")
    assert added
    assert text.endswith("## 배운 점\n- shift+클릭으로 바로 옮긴다 (2026-10-17)\n")
    text, added = games.add_note(text, "  shift+클릭으로   바로 옮긴다 ", "2026-10-18")
    assert not added  # 같은 내용은 건너뛴다 (공백·날짜 무시)
    text, added = games.add_note(text, "침대는 밤에만 쓸 수 있다", "2026-10-18")
    assert text.count("\n- ") == 3 and text.endswith("(2026-10-18)\n")  # 기본 조작 1줄 + 배운 점 2줄


def test_add_note_creates_section_and_keeps_later_sections():
    text, _ = games.add_note("# 게임\n- 조작", "새 사실", "2026-10-17")
    assert text == "# 게임\n- 조작\n\n## 배운 점\n- 새 사실 (2026-10-17)\n"
    middle = "# 게임\n## 배운 점\n- 옛 사실 (2026-01-01)\n\n## 기타\n- 다른 칸\n"
    text, _ = games.add_note(middle, "새 사실", "2026-10-17")
    assert "- 옛 사실 (2026-01-01)\n- 새 사실 (2026-10-17)\n\n## 기타" in text


def test_add_note_rejects_empty_and_truncates():
    with pytest.raises(ValueError):
        games.add_note(MINECRAFT, "   ", "2026-10-17")
    text, _ = games.add_note(MINECRAFT, "가" * 1000, "2026-10-17")
    assert "가" * games.MAX_NOTE_CHARS + " (" in text and "가" * (games.MAX_NOTE_CHARS + 1) not in text


def test_repo_game_files_parse():
    """저장소에 들어 있는 게임 파일이 읽히고 자동 감지되는지."""
    found = games.list_games(Path(__file__).resolve().parent.parent / "games")
    assert "minecraft" in [g.id for g in found]
    assert games.detect("마인크래프트에서 집 짓기", found).id == "minecraft"
