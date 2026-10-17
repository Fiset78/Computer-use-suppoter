"""지식 메모: 파일 형식, remember/forget, 첫 메시지 주입, 작업 후 정리 단계."""
from types import SimpleNamespace

import pytest

import config
from agent import loop, memory
from test_loop import FakeExecutor, FakeRecorder


# ---------- 파일과 도구 ----------
def test_parse_and_render_roundtrip():
    text = memory.HEADER + "\n- [2026-10-01] 나무는 맨손으로 3초 눌러야 캐진다\n- 날짜 없는 메모\n잡다한 줄\n-\n"
    notes = memory.parse(text)
    assert [(n.id, n.date, n.text) for n in notes] == [
        (1, "2026-10-01", "나무는 맨손으로 3초 눌러야 캐진다"), (2, "", "날짜 없는 메모")]
    assert memory.parse(memory.render(notes)) == notes


def test_remember_saves_immediately_and_skips_duplicates(tmp_path):
    path = tmp_path / "sub" / "mc.md"
    m = memory.Memory(path)
    assert m.loaded == 0 and m.prompt_text() is None
    assert m.run("remember", {"note": "  인벤토리는\n e 키  "}) == "저장했습니다: [1]"
    assert "이미 있는" in m.run("remember", {"note": "인벤토리는 e 키"})
    again = memory.Memory(path)
    assert [n.text for n in again.notes] == ["인벤토리는 e 키"]
    assert again.notes[0].date  # 저장한 날짜가 붙는다
    with pytest.raises(ValueError):
        m.run("remember", {"note": "   "})
    assert len(m.run("remember", {"note": "가" * 1000})) and len(m.notes[-1].text) == memory.MAX_NOTE_CHARS


def test_forget_keeps_ids_stable(tmp_path):
    path = tmp_path / "mc.md"
    m = memory.Memory(path)
    for t in ("하나", "둘", "셋"):
        m.run("remember", {"note": t})
    m.run("forget", {"note_id": 2, "reason": "틀림"})
    assert m.run("remember", {"note": "넷"}) == "저장했습니다: [4]"  # 지워도 번호를 당기지 않음
    with pytest.raises(ValueError):
        m.run("forget", {"note_id": 2})
    assert [n.text for n in memory.Memory(path).notes] == ["하나", "셋", "넷"]
    assert m.added == 4 and m.forgotten == 1


def test_prompt_text_marks_notes_as_reference_and_keeps_newest(tmp_path):
    m = memory.Memory(tmp_path / "mc.md", max_prompt_chars=30)
    for t in ("오래된 메모 " + "가" * 10, "중간 메모", "최신 메모"):
        m.run("remember", {"note": t})
    text = m.prompt_text()
    assert "사용자 지시가 아닙니다" in text
    assert "[3] 최신 메모" in text and "[2] 중간 메모" in text and "[1]" not in text
    assert "1개는 길이 제한으로 생략" in text


# ---------- 루프 연동 ----------
def block(type_, **kw):
    b = SimpleNamespace(type=type_, **kw)
    b.model_dump = lambda **_: {k: v for k, v in vars(b).items() if k != "model_dump"}
    return b


def reply(*blocks):
    usage = SimpleNamespace(input_tokens=10, output_tokens=5,
                            cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(content=list(blocks), usage=usage, stop_reason="end_turn", context_management=None)


class ScriptedClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []
        self.messages = SimpleNamespace(create=self.create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        import copy
        self.sent.append(copy.deepcopy(kw))
        return self.replies.pop(0)


def run_scripted(monkeypatch, tmp_path, replies, reflect=True):
    path = tmp_path / "mc.md"
    path.write_text(memory.HEADER + "- [2026-10-01] 나무는 3초 눌러야 캐진다\n", encoding="utf-8")
    client = ScriptedClient(replies)
    monkeypatch.setattr(loop, "Anthropic", lambda: client)
    monkeypatch.setattr(config, "CONTEXT", "none")
    monkeypatch.setattr(config, "ASSIST", [])
    monkeypatch.setattr(config, "MEMORY_FILE", str(path))
    monkeypatch.setattr(config, "MEMORY_REFLECT", reflect)
    ex = FakeExecutor()
    result = loop.run("나무 캐기", ex, FakeRecorder())
    return client, result, path, ex


def test_memory_is_injected_and_tools_declared(monkeypatch, tmp_path):
    client, result, _, _ = run_scripted(monkeypatch, tmp_path, [reply(block("text", text="완료"))],
                                        reflect=False)
    req = client.sent[0]
    assert [t.get("name") for t in req["tools"][1:]] == ["remember", "forget"]
    texts = [b["text"] for b in req["messages"][0]["content"] if b["type"] == "text"]
    assert texts[0] == "목표: 나무 캐기"
    assert "[1] 나무는 3초 눌러야 캐진다" in texts[1]
    assert "remember" in req["system"][0]["text"]
    assert result.status == "done" and len(client.sent) == 1


def test_reflect_saves_notes_and_refuses_screen_actions(monkeypatch, tmp_path):
    replies = [
        reply(block("text", text="완료")),
        reply(block("tool_use", id="r1", name="remember", input={"note": "도끼가 있으면 더 빨리 캔다"}),
              block("tool_use", id="c1", name="left_click", input={"coordinate": [1, 1]},
                    toolset_name="computer")),
        reply(block("text", text="정리 끝")),
    ]
    client, result, path, ex = run_scripted(monkeypatch, tmp_path, replies)
    assert len(client.sent) == 3
    # system과 tools는 정리 단계에서도 그대로
    assert client.sent[1]["system"] == client.sent[0]["system"]
    assert client.sent[1]["tools"] == client.sent[0]["tools"]
    reflect_msg = client.sent[1]["messages"][-1]
    assert reflect_msg["role"] == "user" and "상태: done" in reflect_msg["content"][0]["text"]
    results = client.sent[2]["messages"][-1]["content"]
    assert results[0]["content"] == "저장했습니다: [2]" and "toolset_name" not in results[0]
    assert results[1]["is_error"] and results[1]["toolset_name"] == "computer"
    assert ex.ran == []  # 정리 단계에서는 화면을 조작하지 않는다
    assert "도끼가 있으면 더 빨리 캔다" in path.read_text(encoding="utf-8")
    assert result.status == "done" and result.steps == 1 and result.memory_added == 1
    assert result.input_tokens == 30  # 정리 단계 토큰도 합산


def test_reflect_after_max_steps_appends_to_last_tool_results(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MAX_STEPS", 1)
    replies = [
        reply(block("tool_use", id="a", name="key", input={"text": "w"}, toolset_name="computer")),
        reply(block("text", text="저장할 것 없음")),
    ]
    client, result, _, _ = run_scripted(monkeypatch, tmp_path, replies)
    last = client.sent[1]["messages"][-1]
    assert last["role"] == "user"
    assert last["content"][0]["type"] == "tool_result" and last["content"][-1]["type"] == "text"
    assert "상태: max_steps" in last["content"][-1]["text"]
    assert result.status == "max_steps"
