"""경험 기억 (순수 모듈). 실행 중 만난 문제와 해결 방법을 '교훈'으로 쌓아 두고,
다음 실행을 시작할 때 목표와 비슷한 교훈을 골라 Claude에게 먼저 알려 준다.

모델 가중치를 다시 학습시키는 것이 아니라, 경험을 글로 남겨 다음 실행의 문맥에 넣는 방식이다.
- 기록: Claude가 remember_lesson 도구로 {상황, 문제, 해결, 키워드}를 남긴다. 거의 같은 교훈이 있으면 갱신한다.
- 선택: 목표 문장과 교훈의 글자 조각(한글 두 글자 단위 포함)이 겹치는 정도 × 성공률로 고른다.
- 강화: 교훈을 넣어 준 실행이 성공하면 success, 실패하면 failure가 늘어 다음 선택 순위가 바뀐다.
저장 위치: memory/lessons.json (사람이 읽고 고칠 수 있는 JSON).
"""
import json
import math
import re
import time
import uuid
from pathlib import Path

MAX_LESSONS = 300        # 넘으면 점수가 낮은 교훈부터 지운다
DEFAULT_PICK = 6         # 실행마다 넣어 주는 교훈 수
MIN_RELEVANCE = 0.12     # 이보다 관련도가 낮으면 넣지 않는다
DUPLICATE_SIMILARITY = 0.6

_WORD = re.compile(r"[0-9A-Za-z가-힣]+")


def tokens(text: str) -> set[str]:
    """비교용 조각: 영어/숫자 단어(소문자) + 한글 단어의 두 글자 조각 (조사가 붙어도 겹치게)."""
    out: set[str] = set()
    for w in _WORD.findall((text or "").lower()):
        if re.search(r"[가-힣]", w):
            if len(w) == 1:
                out.add(w)
            else:
                out.update(w[i:i + 2] for i in range(len(w) - 1))
        elif len(w) > 1:
            out.add(w)
    return out


def _lesson_text(lesson: dict) -> str:
    return " ".join([lesson.get("situation", ""), lesson.get("problem", ""), " ".join(lesson.get("keywords", []))])


def relevance(goal: str, lesson: dict) -> float:
    """목표와 교훈이 얼마나 관련 있는지 (0~1 근처). 키워드 일치에 가중치를 더 준다."""
    g = tokens(goal)
    if not g:
        return 0.0
    body = tokens(_lesson_text(lesson))
    keys = tokens(" ".join(lesson.get("keywords", [])))
    if not body:
        return 0.0
    overlap = len(g & body) / math.sqrt(len(g) * len(body))
    key_hit = len(g & keys) / max(1, len(keys)) if keys else 0.0
    return 0.7 * overlap + 0.3 * key_hit


def trust(lesson: dict) -> float:
    """써 본 결과로 매기는 신뢰도 (처음은 0.6, 성공하면 1에 가깝게, 실패가 쌓이면 내려감)."""
    s, f = lesson.get("success", 0), lesson.get("failure", 0)
    return (s + 1.2) / (s + f + 2)


def similarity(a: dict, b: dict) -> float:
    ta = tokens(a.get("situation", "") + " " + a.get("problem", ""))
    tb = tokens(b.get("situation", "") + " " + b.get("problem", ""))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def load(path: Path) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save(path: Path, lessons: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(lessons, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # 쓰다가 꺼져도 파일이 깨지지 않게


def add(lessons: list[dict], situation: str, problem: str, solution: str, keywords: list[str] | None = None,
        now: float | None = None) -> tuple[list[dict], dict, bool]:
    """교훈을 더한다. 거의 같은 상황·문제의 교훈이 있으면 해결 방법을 새로 고친다.
    돌려주는 값: (새 목록, 저장된 교훈, 갱신 여부)."""
    now = now if now is not None else time.time()
    new = {
        "situation": situation.strip(), "problem": problem.strip(), "solution": solution.strip(),
        "keywords": [k.strip() for k in (keywords or []) if k and k.strip()],
    }
    best, best_sim = None, 0.0
    for lesson in lessons:
        sim = similarity(lesson, new)
        if sim > best_sim:
            best, best_sim = lesson, sim
    if best is not None and best_sim >= DUPLICATE_SIMILARITY:
        updated = {**best, **new, "keywords": list(dict.fromkeys(best.get("keywords", []) + new["keywords"])),
                   "updated": now, "revisions": best.get("revisions", 1) + 1}
        return [updated if l is best else l for l in lessons], updated, True
    lesson = {"id": uuid.uuid4().hex[:8], **new, "created": now, "updated": now, "revisions": 1,
              "used": 0, "success": 0, "failure": 0}
    return prune([*lessons, lesson]), lesson, False


def prune(lessons: list[dict], limit: int = MAX_LESSONS) -> list[dict]:
    if len(lessons) <= limit:
        return lessons
    keep = sorted(lessons, key=lambda l: (trust(l), l.get("updated", 0)), reverse=True)[:limit]
    ids = {l["id"] for l in keep}
    return [l for l in lessons if l["id"] in ids]


def pick(lessons: list[dict], goal: str, k: int = DEFAULT_PICK) -> list[dict]:
    """목표와 관련 있는 교훈만 골라 (관련도 × 신뢰도) 순으로 k개."""
    scored = []
    for l in lessons:
        rel = relevance(goal, l)
        if rel >= MIN_RELEVANCE:
            scored.append((rel * trust(l), l))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [l for _, l in scored[:k]]


def as_prompt(picked: list[dict]) -> str:
    """새 실행의 첫 메시지에 붙일 글."""
    if not picked:
        return ""
    lines = ["[이전 실행에서 배운 점] 비슷한 상황에서 겪은 문제와 통했던 방법입니다. 맞는 상황이면 처음부터 이 방법을 쓰세요."]
    for i, l in enumerate(picked, 1):
        lines.append(f"{i}. 상황: {l['situation']} / 문제: {l['problem']} / 해결: {l['solution']}")
    return "\n".join(lines)


def feedback(lessons: list[dict], used_ids: list[str], succeeded: bool, now: float | None = None) -> list[dict]:
    """넣어 준 교훈들의 사용·성공·실패 횟수를 갱신한다."""
    now = now if now is not None else time.time()
    ids = set(used_ids)
    out = []
    for l in lessons:
        if l.get("id") in ids:
            l = {**l, "used": l.get("used", 0) + 1, "last_used": now,
                 "success" if succeeded else "failure": l.get("success" if succeeded else "failure", 0) + 1}
        out.append(l)
    return out
