import copy

import pytest

from agent import context


def img(tag="x"):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": tag}}


def tool_result(id, *blocks):
    return {"type": "tool_result", "tool_use_id": id, "toolset_name": "computer", "content": list(blocks)}


def conversation(n_turns):
    """첫 user 메시지(스크린샷 1장) + n_turns번의 (assistant, user[tool_result + 스크린샷])"""
    msgs = [{"role": "user", "content": [{"type": "text", "text": "목표"}, img("init")]}]
    for i in range(n_turns):
        msgs.append({"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": "left_click", "input": {}}]})
        msgs.append({"role": "user", "content": [tool_result(f"t{i}", {"type": "text", "text": "OK"}, img(str(i)))]})
    return msgs


def test_resolve_strategy():
    assert context.resolve_strategy("server", "claude-sonnet-5") == ("server", None)
    assert context.resolve_strategy("prune", "claude-sonnet-5") == ("prune", None)
    strategy, warning = context.resolve_strategy("prune", "claude-opus-5-5")
    assert strategy == "server" and warning
    assert context.resolve_strategy("prune", "claude-fable-5-1")[0] == "server"
    with pytest.raises(ValueError):
        context.resolve_strategy("summarize", "claude-sonnet-5")


def test_clear_edit_shape():
    edit = context.clear_tool_uses_edit(40000, 6, 10000)
    assert edit == {
        "type": "clear_tool_uses_20250919",
        "trigger": {"type": "input_tokens", "value": 40000},
        "keep": {"type": "tool_uses", "value": 6},
        "clear_at_least": {"type": "input_tokens", "value": 10000},
    }


def test_system_blocks_cache():
    assert context.system_blocks("s")[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in context.system_blocks("s", cache=False)[0]


def test_cache_breakpoints_on_last_three_user_turns_without_mutating():
    msgs = conversation(4)
    original = copy.deepcopy(msgs)
    out = context.with_cache_breakpoints(msgs)
    assert msgs == original  # 저장된 기록은 그대로
    marked = [i for i, m in enumerate(out)
              if m["role"] == "user" and "cache_control" in m["content"][-1]]
    assert marked == [4, 6, 8]  # 최근 user 메시지 3개
    assert all("cache_control" not in b for m in out for b in m["content"] if m["role"] == "assistant")


def test_cache_breakpoints_short_conversation():
    out = context.with_cache_breakpoints(conversation(0))
    assert out[0]["content"][-1]["cache_control"] == {"type": "ephemeral"}


def test_count_images_includes_tool_results():
    assert context.count_images(conversation(3)) == 4


def test_prune_waits_for_batch_then_keeps_latest():
    msgs = conversation(5)  # 6장
    assert context.prune_images(msgs, keep=3, batch=3) == 0
    msgs = conversation(6)  # 7장 > 3 + 3
    assert context.prune_images(msgs, keep=3, batch=3) == 4
    assert context.count_images(msgs) == 3
    # 최근 3장(3, 4, 5번 턴)만 남고, 지운 자리는 텍스트로 바뀐다
    remaining = [b["source"]["data"] for m in msgs if m["role"] == "user"
                 for blk in m["content"] if blk.get("type") == "tool_result"
                 for b in blk["content"] if b["type"] == "image"]
    assert remaining == ["3", "4", "5"]
    assert msgs[0]["content"][1] == {"type": "text", "text": context.PRUNED_PLACEHOLDER}
    # tool_result 구조와 toolset_name은 유지된다
    assert msgs[2]["content"][0]["toolset_name"] == "computer"


def test_prune_is_stable_between_batches():
    msgs = conversation(6)
    context.prune_images(msgs, keep=3, batch=3)
    snapshot = copy.deepcopy(msgs)
    # 다음 몇 턴은 batch를 넘지 않으므로 앞부분(캐시되는 접두부)이 그대로다
    msgs += conversation(2)[1:]
    assert context.prune_images(msgs, keep=3, batch=3) == 0
    assert msgs[: len(snapshot)] == snapshot
