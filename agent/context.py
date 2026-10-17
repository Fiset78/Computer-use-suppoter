"""컨텍스트 관리 (로드맵 6단계). GUI/API 의존성이 없는 순수 모듈이다.

스크린샷은 한 장에 입력 토큰 약 1,000~1,800개라 루프가 길어지면 빠르게 쌓인다. 세 가지를 조합한다.

1. prompt caching 중단점: 매 요청마다 이전까지의 대화를 캐시에서 읽게 한다 (모든 전략 공통).
   - system 블록(도구 정의 포함) 1개 + 최근 user 메시지 3개의 마지막 블록 = 최대 4개
   - 저장된 대화 기록은 건드리지 않고, 요청 직전에 사본에만 표시한다
2. "server": 서버 측 tool result clearing (clear_tool_uses_20250919).
   오래된 tool_result를 서버가 지운다. 우리가 보낸 대화 기록 자체는 바뀌지 않으므로
   preserved thinking 모델(Opus 5.5, Fable 5.1)에서도 안전하다. 권장 기본값.
3. "prune": 클라이언트 측 가지치기. 스크린샷이 keep + batch 장을 넘으면 최근 keep 장만 남긴다.
   매 턴 지우면 캐시가 매번 깨지므로 몰아서 지운다.
   preserved thinking 모델에서는 이후 thinking 블록이 무효가 되므로 쓰지 않는다.
"""
CONTEXT_STRATEGIES = ("server", "prune", "none")
CONTEXT_MANAGEMENT_BETA = "context-management-2025-06-27"
PRUNED_PLACEHOLDER = "[이전 스크린샷 생략: 컨텍스트 절약을 위해 제거됨]"

# 대화 기록을 바꾸면(클라이언트 가지치기) 이후 thinking 블록이 무효가 되는 모델
PRESERVED_THINKING_MODELS = ("claude-opus-5-5", "claude-fable-5-1")

EPHEMERAL = {"type": "ephemeral"}


def uses_preserved_thinking(model: str) -> bool:
    return any(model.startswith(m) for m in PRESERVED_THINKING_MODELS)


def resolve_strategy(strategy: str, model: str) -> tuple[str, str | None]:
    """(실제로 쓸 전략, 경고 문구). preserved thinking 모델에서 prune은 server로 바꾼다."""
    if strategy not in CONTEXT_STRATEGIES:
        raise ValueError(f"알 수 없는 컨텍스트 전략: {strategy} (사용 가능: {', '.join(CONTEXT_STRATEGIES)})")
    if strategy == "prune" and uses_preserved_thinking(model):
        return "server", (f"{model}은(는) 대화 기록을 고치면 thinking 블록이 무효가 되므로 "
                          "prune 대신 server(서버 측 tool result clearing)를 씁니다.")
    return strategy, None


def clear_tool_uses_edit(trigger_tokens: int, keep_tool_uses: int, clear_at_least_tokens: int) -> dict:
    """서버 측 tool result clearing 설정.
    clear_at_least: 지울 때마다 캐시가 깨지므로, 한 번에 충분히 지워서 캐시 재작성 비용을 상쇄한다."""
    return {
        "type": "clear_tool_uses_20250919",
        "trigger": {"type": "input_tokens", "value": trigger_tokens},
        "keep": {"type": "tool_uses", "value": keep_tool_uses},
        "clear_at_least": {"type": "input_tokens", "value": clear_at_least_tokens},
    }


def system_blocks(text: str, cache: bool = True) -> list[dict]:
    block = {"type": "text", "text": text}
    if cache:
        block["cache_control"] = dict(EPHEMERAL)
    return [block]


def with_cache_breakpoints(messages: list[dict], recent: int = 3) -> list[dict]:
    """최근 user 메시지 recent개의 마지막 블록에 cache_control을 붙인 사본을 돌려준다.
    원본(저장된 대화 기록)은 바꾸지 않는다. 표시 위치는 매 턴 앞으로 이동한다."""
    out = list(messages)
    marked = 0
    for i in range(len(out) - 1, -1, -1):
        if marked >= recent:
            break
        msg = out[i]
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not content:
            continue
        content = list(content)
        last = dict(content[-1])
        last["cache_control"] = dict(EPHEMERAL)
        content[-1] = last
        out[i] = {**msg, "content": content}
        marked += 1
    return out


def _image_slots(messages: list[dict]) -> list[tuple[list, int]]:
    """대화 속 모든 이미지 블록의 위치 (담긴 리스트, 인덱스)를 오래된 순서로."""
    slots = []
    for msg in messages:
        if msg.get("role") != "user" or not isinstance(msg.get("content"), list):
            continue
        for i, block in enumerate(msg["content"]):
            if block.get("type") == "image":
                slots.append((msg["content"], i))
            elif block.get("type") == "tool_result" and isinstance(block.get("content"), list):
                for j, inner in enumerate(block["content"]):
                    if inner.get("type") == "image":
                        slots.append((block["content"], j))
    return slots


def count_images(messages: list[dict]) -> int:
    return len(_image_slots(messages))


def prune_images(messages: list[dict], keep: int, batch: int) -> int:
    """이미지가 keep + batch장을 넘으면 최근 keep장만 남기고 나머지를 자리표시 텍스트로 바꾼다.
    대화 기록을 제자리에서 수정하고, 지운 장수를 돌려준다. 넘지 않으면 아무것도 하지 않는다."""
    slots = _image_slots(messages)
    if len(slots) <= keep + batch:
        return 0
    old = slots[: len(slots) - keep] if keep > 0 else slots
    for container, idx in old:
        container[idx] = {"type": "text", "text": PRUNED_PLACEHOLDER}
    return len(old)
