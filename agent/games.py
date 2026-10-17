"""게임 지식 파일 (순수 모듈). 게임마다 조작법·기초 플레이 지식을 적은 마크다운 파일을 두고,
실행할 때 그 내용을 Claude에게 먼저 알려 준다.

- 위치: <GAMES_DIR>/<id>.md (기본 games/). 이름이 '_'로 시작하는 파일(서식 견본 등)은 게임으로 치지 않는다
- 이름: `이름: 마인크래프트, minecraft` 줄에 적은 이름과 파일 이름(id)으로 게임을 찾는다
- 고르기: 직접 지정(--game, PC_AGENT_GAME)이 먼저, 없으면 목표 문장에 나온 게임 이름으로 자동 감지
- 배운 점: Claude가 add_game_note 도구로 파일 끝 '## 배운 점' 칸에 한 줄씩 덧붙인다 (같은 내용은 건너뜀)
"""
import re
from dataclasses import dataclass
from pathlib import Path

NOTES_HEADING = "## 배운 점"
MAX_NOTE_CHARS = 300
OFF = ("none", "off", "0", "끔", "없음")  # 게임 지식을 쓰지 않는 지정 값

_NAMES_LINE = re.compile(r"^\s*이름\s*:\s*(.+)$", re.MULTILINE)
_TITLE_LINE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@dataclass
class Game:
    id: str              # 파일 이름 (확장자 제외)
    title: str           # 첫 '# ' 제목, 없으면 id
    names: list[str]     # 찾을 때 쓰는 이름 (id 포함)
    path: Path


def parse(text: str, game_id: str, path: Path) -> Game:
    m = _TITLE_LINE.search(text)
    title = m.group(1).strip() if m else game_id
    names = [game_id]
    m = _NAMES_LINE.search(text)
    if m:
        for name in m.group(1).split(","):
            name = name.strip()
            if name and name.lower() not in (n.lower() for n in names):
                names.append(name)
    return Game(game_id, title, names, path)


def list_games(games_dir: str | Path) -> list[Game]:
    folder = Path(games_dir)
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob("*.md")):
        if path.stem.startswith("_"):
            continue
        try:
            out.append(parse(path.read_text(encoding="utf-8-sig"), path.stem, path))
        except OSError:
            continue
    return out


def detect(goal: str, games: list[Game]) -> Game | None:
    """목표 문장에 이름이 나온 게임. 여럿이면 가장 긴 이름이 맞은 게임 (조사가 붙어도 찾게 부분 일치)."""
    text = (goal or "").lower()
    best, best_len = None, 0
    for game in games:
        for name in game.names:
            if len(name) > best_len and name.lower() in text:
                best, best_len = game, len(name)
    return best


def find(choice: str, games: list[Game]) -> Game | None:
    key = choice.strip().lower()
    for game in games:
        if key in (n.lower() for n in game.names):
            return game
    return None


def resolve(choice: str, goal: str, games: list[Game]) -> Game | None:
    """쓸 게임을 고른다. choice가 비면 자동 감지, OFF 값이면 None, 모르는 이름이면 ValueError."""
    choice = (choice or "").strip()
    if not choice:
        return detect(goal, games)
    if choice.lower() in OFF:
        return None
    game = find(choice, games)
    if game is None:
        known = ", ".join(g.id for g in games) or "(없음)"
        raise ValueError(f"게임 지식 파일을 찾지 못했습니다: {choice} (있는 게임: {known})")
    return game


def load(choice: str, goal: str, games_dir: str | Path) -> tuple[Game | None, str]:
    """resolve로 고른 게임과 파일 내용. 고른 게임이 없으면 (None, "")."""
    game = resolve(choice, goal, list_games(games_dir))
    if game is None:
        return None, ""
    return game, game.path.read_text(encoding="utf-8-sig")


def as_prompt(game: Game, text: str) -> str:
    """첫 메시지에 넣을 게임 지식."""
    return (f"[게임 지식: {game.title}]\n"
            f"사람이 정리한 이 게임의 조작법과 기초 지식입니다 ({game.path.as_posix()}). "
            "'배운 점'은 이전 실행에서 직접 확인해 덧붙인 내용입니다.\n\n"
            f"{text.strip()}\n[게임 지식 끝]")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def add_note(text: str, note: str, date: str) -> tuple[str, bool]:
    """'## 배운 점' 칸 끝에 '- note (date)'를 덧붙인 새 내용과, 실제로 더했는지를 돌려준다.
    칸이 없으면 파일 끝에 만든다. 같은 내용(날짜 제외)이 이미 있으면 그대로 둔다."""
    note = " ".join(note.split())[:MAX_NOTE_CHARS]
    if not note:
        raise ValueError("배운 점이 비어 있습니다.")
    lines = text.rstrip("\n").split("\n") if text.strip() else []
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == NOTES_HEADING)
    except StopIteration:
        lines += (["", NOTES_HEADING] if lines else [NOTES_HEADING])
        start = len(lines) - 1
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    for line in lines[start + 1:end]:
        body = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)\s*$", "", line.strip().removeprefix("- "))
        if _norm(body) == _norm(note):
            return text, False
    insert = end
    while insert > start + 1 and not lines[insert - 1].strip():
        insert -= 1  # 칸 끝의 빈 줄 앞에 붙인다
    lines.insert(insert, f"- {note} ({date})")
    return "\n".join(lines) + "\n", True
