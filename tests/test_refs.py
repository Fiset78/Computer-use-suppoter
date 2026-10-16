"""참고 자료 고르기: 파일 → content 블록, 번호 선택, 시작 메뉴, 첫 메시지 주입, prune 보호."""
import base64

import pytest

import config
from agent import context, loop, refs


@pytest.fixture
def files(tmp_path):
    (tmp_path / "조작법.md").write_text("인벤토리: e\n달리기: ctrl", encoding="utf-8")
    (tmp_path / "옛날.txt").write_bytes("cp949 메모".encode("cp949"))
    (tmp_path / "제작법.png").write_bytes(b"\x89PNG fake")
    (tmp_path / "설명서.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "game.exe").write_bytes(b"MZ")
    return tmp_path


def test_load_makes_blocks_per_type(files):
    out = refs.load([files / "조작법.md", files / "옛날.txt", files / "제작법.png", files / "설명서.pdf",
                     files / "game.exe", files / "없음.md"])
    types = [b["type"] for b in out.blocks]
    assert types == ["text", "text", "text", "text", "image", "text", "document"]
    assert out.blocks[0]["text"] == refs.INTRO
    assert out.blocks[1]["text"].startswith("[참고 자료: 조작법.md]\n인벤토리: e")
    assert "cp949 메모" in out.blocks[2]["text"]
    assert out.blocks[4]["source"]["media_type"] == "image/png"
    assert base64.b64decode(out.blocks[4]["source"]["data"]) == b"\x89PNG fake"
    assert out.blocks[6]["source"]["media_type"] == "application/pdf" and out.blocks[6]["title"] == "설명서.pdf"
    assert out.images == [out.blocks[4]]
    assert len(out.used) == 4 and len(out.skipped) == 2
    assert any("지원하지 않는 형식" in s for s in out.skipped)


def test_load_text_budget(files):
    (files / "긴글.md").write_text("가" * 50, encoding="utf-8")
    out = refs.load([files / "긴글.md", files / "조작법.md"], max_text_chars=30)
    assert "뒷부분 생략" in out.blocks[1]["text"] and out.blocks[1]["text"].endswith("가" * 30)
    assert out.used == [str(files / "긴글.md")] and "제한" in out.skipped[0]


def test_load_nothing_gives_no_intro():
    assert refs.load([]).blocks == []


def test_parse_selection():
    assert refs.parse_selection("1, 3-4", 5) == [0, 2, 3]
    assert refs.parse_selection("2,2", 3) == [1]
    for bad in ("6", "0", "a", "2-x"):
        with pytest.raises(ValueError):
            refs.parse_selection(bad, 5)


def test_candidates(files):
    assert [p.name for p in refs.candidates(files)] == ["설명서.pdf", "옛날.txt", "제작법.png", "조작법.md"]
    assert [p.name for p in refs.candidates(files, memory=True)] == ["조작법.md"]
    assert refs.candidates(files / "없는폴더") == []


def menu(tmp_path, answers, **kw):
    mem_dir, ref_dir = tmp_path / "memory", tmp_path / "refs"
    mem_dir.mkdir(exist_ok=True)
    ref_dir.mkdir(exist_ok=True)
    (mem_dir / "mc.md").write_text("- a", encoding="utf-8")
    (mem_dir / "desk.md").write_text("- b", encoding="utf-8")
    (ref_dir / "a.md").write_text("A", encoding="utf-8")
    (ref_dir / "b.png").write_bytes(b"x")
    printed = []
    it = iter(answers)
    result = refs.pick(mem_dir, ref_dir, input_fn=lambda _: next(it), print_fn=printed.append, **kw)
    return result, printed, mem_dir, ref_dir


def test_pick_by_number(tmp_path):
    (memory, chosen), _, mem_dir, ref_dir = menu(tmp_path, ["2", "1,2"])
    assert memory == str(mem_dir / "mc.md")  # 이름순: desk.md, mc.md
    assert chosen == [str(ref_dir / "a.md"), str(ref_dir / "b.png")]


def test_pick_new_memory_name_and_retry_on_bad_input(tmp_path):
    (memory, chosen), printed, mem_dir, _ = menu(tmp_path, ["9", "a/b", "마크", "0"])
    assert memory == str(mem_dir / "마크.md") and chosen == []
    assert sum("다시 입력하세요" in p for p in printed) == 2


def test_pick_enter_keeps_current(tmp_path):
    (memory, chosen), printed, _, _ = menu(tmp_path, ["", ""], current_memory="memory/x.md",
                                           current_refs=["refs/c.md"])
    assert memory == "memory/x.md" and chosen == ["refs/c.md"]
    (memory, chosen), _, _, _ = menu(tmp_path, ["0", ""])
    assert memory == "" and chosen == []


def test_prune_protects_reference_images():
    ref_img = {"type": "image", "source": {}}
    shots = [{"type": "image", "source": {}} for _ in range(5)]
    messages = [{"role": "user", "content": [ref_img, shots[0]]}] + [
        {"role": "user", "content": [s]} for s in shots[1:]]
    assert context.prune_images(messages, keep=1, batch=1, protect=[ref_img]) == 4
    assert messages[0]["content"][0] is ref_img
    assert context.count_images(messages) == 2


def test_loop_puts_refs_in_first_message(monkeypatch, files):
    from test_loop import FakeExecutor, FakeRecorder, run_with

    monkeypatch.setattr(config, "REFS", [str(files / "조작법.md"), str(files / "제작법.png")])
    monkeypatch.setattr(config, "MEMORY_FILE", "")
    client, _ = run_with(monkeypatch, "none")
    content = client.plain[0]["messages"][0]["content"]
    types = [b["type"] for b in content]
    assert content[0]["text"].startswith("목표:")
    assert types == ["text", "text", "text", "text", "image", "text", "image"]  # 마지막 image가 현재 화면
    assert content[-2]["text"] == "아래는 현재 화면입니다."


def test_main_cli_options(monkeypatch, tmp_path):
    import main

    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path / "m"))
    monkeypatch.setattr(config, "REFS_DIR", str(tmp_path / "r"))
    args = main.parse_args(["--memory", "none", "--ref", "a.md,b.png", "--ref", "c.pdf", "나무", "캐기"])
    assert args.goal == ["나무", "캐기"]
    main.choose_files(args)  # 폴더가 비어 있으면 메뉴 없이 진행
    assert config.MEMORY_FILE == "" and config.REFS == ["a.md", "b.png", "c.pdf"]
