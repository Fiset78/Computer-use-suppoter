"""computer_toolset 규칙 검증: 결과 개수/순서, toolset_name, 실패 후 미실행 처리."""
from types import SimpleNamespace

import config
from agent import loop


def tool_use(id, name, computer=True, **inp):
    b = SimpleNamespace(type="tool_use", id=id, name=name, input=inp)
    if computer:
        b.toolset_name = "computer"
    return b


class FakeRecorder:
    def __init__(self):
        self.events = []

    def event(self, kind, **data):
        self.events.append((kind, data))


class FakeExecutor:
    def __init__(self, fail_on=()):
        self.fail_on = set(fail_on)
        self.ran = []

    def run(self, name, inp):
        self.ran.append(name)
        if name in self.fail_on:
            raise RuntimeError("boom")
        return "OK"

    def screenshot_block(self, label):
        return {"type": "image", "label": label}


class FakeAssist:
    names = ["list_ui_elements", "click_element"]

    def __init__(self, fail_on=()):
        self.fail_on = set(fail_on)
        self.ran = []

    def has(self, name):
        return name in self.names

    def run(self, name, inp):
        self.ran.append(name)
        if name in self.fail_on:
            raise LookupError("gone")
        return "목록"


def response(*blocks):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text="..."), *blocks])


def test_all_results_in_order_with_toolset_name_only_on_computer():
    ex, assist = FakeExecutor(), FakeAssist()
    res = loop.process_tool_calls(
        response(tool_use("a", "left_click"), tool_use("b", "list_ui_elements", computer=False),
                 tool_use("c", "click_element", computer=False)),
        ex, FakeRecorder(), assist)
    assert [r["tool_use_id"] for r in res] == ["a", "b", "c"]
    assert res[0]["toolset_name"] == "computer"
    assert "toolset_name" not in res[1] and "toolset_name" not in res[2]
    # 마지막이 화면을 바꾸는 도구면 자동 스크린샷이 붙는다
    assert res[2]["content"][-1]["type"] == "image"


def test_failure_skips_rest_with_exact_text():
    ex, assist = FakeExecutor(fail_on={"left_click"}), FakeAssist()
    res = loop.process_tool_calls(
        response(tool_use("a", "left_click"), tool_use("b", "type", text="x"),
                 tool_use("c", "click_element", computer=False, element_id=1)),
        ex, FakeRecorder(), assist)
    assert res[0]["is_error"] and res[0]["content"].startswith("Error:")
    assert res[1] == {"type": "tool_result", "tool_use_id": "b", "toolset_name": "computer",
                      "content": "Not executed: an earlier computer action in this turn failed.",
                      "is_error": True}
    assert res[2]["is_error"] and "toolset_name" not in res[2]
    assert ex.ran == ["left_click"] and assist.ran == []


def test_custom_tool_failure_also_stops_later_computer_actions():
    ex, assist = FakeExecutor(), FakeAssist(fail_on={"click_element"})
    res = loop.process_tool_calls(
        response(tool_use("a", "click_element", computer=False, element_id=9), tool_use("b", "key", text="Return")),
        ex, FakeRecorder(), assist)
    assert res[0]["is_error"]
    assert res[1]["content"] == loop.NOT_EXECUTED and res[1]["toolset_name"] == "computer"
    assert ex.ran == []


def test_unknown_custom_tool_is_error_when_assist_off():
    res = loop.process_tool_calls(
        response(tool_use("a", "click_element", computer=False, element_id=1)),
        FakeExecutor(), FakeRecorder(), None)
    assert res[0]["is_error"] and "Unknown tool" in res[0]["content"]


def test_no_auto_screenshot_after_observe_tool(monkeypatch):
    monkeypatch.setattr(config, "AUTO_SCREENSHOT", True)
    res = loop.process_tool_calls(
        response(tool_use("a", "left_click"), tool_use("b", "list_ui_elements", computer=False)),
        FakeExecutor(), FakeRecorder(), FakeAssist())
    assert res[1]["content"] == "목록"


def test_no_tool_calls_returns_empty():
    assert loop.process_tool_calls(response(), FakeExecutor(), FakeRecorder(), None) == []


def test_system_prompt_includes_hints_only_when_assist_on():
    assert loop.build_system_prompt(None) == loop.SYSTEM_PROMPT

    class A:
        names = ["wait_for_change"]

        def prompt_hints(self):
            return "- 힌트"

    assert loop.build_system_prompt(A()).endswith("보조 도구:\n- 힌트\n")


# ---------- run(): 요청 형태 (컨텍스트 전략, 캐시 중단점) ----------
class FakeAPI:
    def __init__(self, sent):
        self.sent = sent

    def create(self, **kw):
        self.sent.append(kw)
        usage = SimpleNamespace(input_tokens=10, output_tokens=5,
                                cache_read_input_tokens=100, cache_creation_input_tokens=20)
        cm = SimpleNamespace(applied_edits=[SimpleNamespace(
            model_dump=lambda **_: {"type": "clear_tool_uses_20250919", "cleared_tool_uses": 4})])
        text = SimpleNamespace(type="text", text="완료",
                               model_dump=lambda **_: {"type": "text", "text": "완료"})
        return SimpleNamespace(content=[text],
                               usage=usage, stop_reason="end_turn", context_management=cm)


class FakeClient:
    def __init__(self):
        self.plain, self.beta_sent = [], []
        self.messages = FakeAPI(self.plain)
        self.beta = SimpleNamespace(messages=FakeAPI(self.beta_sent))


def run_with(monkeypatch, strategy, model="claude-sonnet-5"):
    client = FakeClient()
    monkeypatch.setattr(loop, "Anthropic", lambda: client)
    monkeypatch.setattr(config, "CONTEXT", strategy)
    monkeypatch.setattr(config, "MODEL", model)
    monkeypatch.setattr(config, "ASSIST", [])
    monkeypatch.setattr(config, "PROMPT_CACHE", True)
    result = loop.run("목표", FakeExecutor(), FakeRecorder())
    return client, result


def test_run_server_strategy_uses_beta_context_management(monkeypatch):
    client, result = run_with(monkeypatch, "server")
    assert client.plain == [] and len(client.beta_sent) == 1
    req = client.beta_sent[0]
    assert req["betas"] == ["context-management-2025-06-27"]
    assert req["context_management"]["edits"][0]["type"] == "clear_tool_uses_20250919"
    assert req["tools"] == [{"type": "computer_toolset_20260801"}]
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["messages"][0]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert result.status == "done"
    assert result.cache_read_tokens == 100 and result.cache_write_tokens == 20
    assert result.cleared_tool_uses == 4


def test_run_prune_and_none_use_plain_endpoint(monkeypatch):
    for strategy in ("prune", "none"):
        client, _ = run_with(monkeypatch, strategy)
        assert client.beta_sent == [] and len(client.plain) == 1
        assert "context_management" not in client.plain[0]


def test_run_prune_on_preserved_thinking_model_switches_to_server(monkeypatch):
    client, _ = run_with(monkeypatch, "prune", model="claude-opus-5-5")
    assert client.plain == [] and len(client.beta_sent) == 1
