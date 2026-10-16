"""참고 자료 고르기 (PC_AGENT_REFS, main.py 시작 메뉴).

- 사용자가 고른 파일(공략 메모, 조작법, 제작법 그림, 설명서 PDF 등)을 첫 user 메시지에 넣는다.
  system과 tools는 바꾸지 않으므로 실행 중 캐시 규칙과 맞는다.
- 지원 형식: 텍스트(.md .txt .json .csv 등) → text 블록, 이미지(.png .jpg .gif .webp) → image 블록,
  PDF → document 블록. 크기 제한을 넘거나 모르는 형식은 이유와 함께 건너뛴다.
- 참고 자료는 읽기 전용이다. Claude가 고치는 파일은 지식 메모(agent/memory.py) 하나뿐이다.
- 시작 메뉴: memory/ 폴더의 메모 파일 하나와 refs/ 폴더의 참고 자료 여러 개를 번호로 고른다.

GUI 의존성이 없어 Linux에서도 테스트한다 (메뉴는 input/print를 주입받는다).
"""
import base64
from dataclasses import dataclass, field
from pathlib import Path

TEXT_EXT = {".md", ".txt", ".json", ".csv", ".yaml", ".yml", ".log"}
IMAGE_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".gif": "image/gif", ".webp": "image/webp"}
PDF_EXT = {".pdf"}
MAX_BINARY_BYTES = 5 * 1024 * 1024  # 이미지/PDF 한 개 최대 크기

INTRO = ("아래는 사용자가 이번 작업에 참고하라고 고른 자료입니다. 화면과 다르면 화면을 우선하세요.")


def supported(path: Path) -> bool:
    ext = path.suffix.lower()
    return ext in TEXT_EXT or ext in IMAGE_EXT or ext in PDF_EXT


@dataclass
class LoadedRefs:
    blocks: list[dict] = field(default_factory=list)   # 첫 메시지에 넣을 content 블록
    used: list[str] = field(default_factory=list)      # 넣은 파일
    skipped: list[str] = field(default_factory=list)   # "파일: 이유"
    images: list[dict] = field(default_factory=list)   # prune 전략이 지우면 안 되는 이미지 블록


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def load(paths: list[str | Path], max_text_chars: int = 20000) -> LoadedRefs:
    """파일들을 content 블록으로 만든다. 텍스트는 모두 합쳐 max_text_chars까지만 넣는다."""
    out = LoadedRefs()
    budget = max_text_chars
    for p in paths:
        path = Path(p)
        name = path.name
        if not path.is_file():
            out.skipped.append(f"{p}: 파일이 없습니다")
            continue
        ext = path.suffix.lower()
        if ext in TEXT_EXT:
            text = _read_text(path).strip()
            if not text:
                out.skipped.append(f"{p}: 빈 파일")
                continue
            if budget <= 0:
                out.skipped.append(f"{p}: 텍스트 글자 수 제한({max_text_chars:,}자) 초과")
                continue
            cut = len(text) > budget
            text = text[:budget]
            budget -= len(text)
            note = " (길이 제한으로 뒷부분 생략)" if cut else ""
            out.blocks.append({"type": "text", "text": f"[참고 자료: {name}]{note}\n{text}"})
        elif ext in IMAGE_EXT or ext in PDF_EXT:
            data = path.read_bytes()
            if len(data) > MAX_BINARY_BYTES:
                out.skipped.append(f"{p}: {MAX_BINARY_BYTES // (1024 * 1024)}MB 초과")
                continue
            b64 = base64.b64encode(data).decode()
            out.blocks.append({"type": "text", "text": f"[참고 자료: {name}]"})
            if ext in IMAGE_EXT:
                block = {"type": "image", "source": {"type": "base64", "media_type": IMAGE_EXT[ext], "data": b64}}
                out.images.append(block)
            else:
                block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                        "data": b64}, "title": name}
            out.blocks.append(block)
        else:
            out.skipped.append(f"{p}: 지원하지 않는 형식 ({ext or '확장자 없음'})")
            continue
        out.used.append(str(p))
    if out.blocks:
        out.blocks.insert(0, {"type": "text", "text": INTRO})
    return out


def parse_paths(text: str | None) -> list[str]:
    """"a.md, refs/b.png" -> ["a.md", "refs/b.png"]"""
    return [t.strip() for t in (text or "").split(",") if t.strip()]


# ---------- 시작 메뉴 ----------
def candidates(folder: str | Path, memory: bool = False) -> list[Path]:
    d = Path(folder)
    if not d.is_dir():
        return []
    files = [p for p in d.iterdir() if p.is_file() and not p.name.startswith(".")]
    files = [p for p in files if (p.suffix.lower() == ".md" if memory else supported(p))]
    return sorted(files, key=lambda p: p.name.lower())


def parse_selection(text: str, count: int) -> list[int]:
    """"1, 3-4" -> [0, 2, 3] (0부터). 범위를 벗어나거나 형식이 틀리면 ValueError."""
    picked: list[int] = []
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            nums = range(int(a), int(b) + 1)
        else:
            nums = [int(part)]
        for n in nums:
            if not 1 <= n <= count:
                raise ValueError(f"{n}번은 없습니다 (1~{count})")
            if n - 1 not in picked:
                picked.append(n - 1)
    return picked


def _ask(prompt: str, input_fn, print_fn, parse):
    while True:
        ans = input_fn(prompt).strip()
        try:
            return parse(ans)
        except ValueError as err:
            print_fn(f"  다시 입력하세요: {err}")


def pick(memory_dir: str | Path, refs_dir: str | Path, current_memory: str = "", current_refs=(),
         input_fn=input, print_fn=print) -> tuple[str, list[str]]:
    """메모 파일 하나와 참고 자료 여러 개를 고른다. (메모 경로 또는 "", 참고 자료 경로 목록)"""
    memories = candidates(memory_dir, memory=True)
    refs = candidates(refs_dir)

    print_fn(f"\n=== 지식 메모 ({memory_dir}/) — Claude가 읽고 고치는 파일 하나 ===")
    for i, p in enumerate(memories, 1):
        mark = " (현재)" if current_memory and Path(current_memory) == p else ""
        print_fn(f"  {i}. {p.name}{mark}")
    print_fn("  0. 쓰지 않음   |   새 이름 입력 → 새 메모 파일   |   Enter → " +
             (f"현재 설정 유지 ({current_memory})" if current_memory else "쓰지 않음"))

    def parse_memory(ans: str) -> str:
        if not ans:
            return current_memory
        if ans == "0":
            return ""
        if ans.isdigit():
            return str(memories[parse_selection(ans, len(memories))[0]])
        name = ans if ans.lower().endswith(".md") else ans + ".md"
        if any(c in name for c in '\\/:*?"<>|'):
            raise ValueError("파일 이름에 쓸 수 없는 문자가 있습니다")
        return str(Path(memory_dir) / name)

    memory = _ask("메모 선택: ", input_fn, print_fn, parse_memory)

    chosen = list(current_refs)
    if refs:
        print_fn(f"\n=== 참고 자료 ({refs_dir}/) — 읽기 전용, 여러 개 선택 가능 ===")
        for i, p in enumerate(refs, 1):
            mark = " (현재)" if str(p) in chosen else ""
            print_fn(f"  {i}. {p.name}{mark}")
        print_fn("  예: 1,3 또는 2-4   |   0 → 고르지 않음   |   Enter → " +
                 ("현재 설정 유지" if chosen else "고르지 않음"))

        def parse_refs(ans: str) -> list[str]:
            if not ans:
                return chosen
            if ans == "0":
                return []
            return [str(refs[i]) for i in parse_selection(ans, len(refs))]

        chosen = _ask("참고 자료 선택: ", input_fn, print_fn, parse_refs)
    else:
        print_fn(f"\n(참고 자료를 쓰려면 {refs_dir}/ 폴더에 파일을 넣으세요)")
    return memory, chosen
