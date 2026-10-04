"""SDK 엔진: API 키 없이 Claude 구독(Claude Code 로그인)으로 에이전트를 돌린다.

Claude Agent SDK가 Claude Code CLI를 띄우고 에이전트 루프(요청 → 도구 실행 → 반복)를 대신 돌린다.
우리는 도구만 in-process MCP 서버로 제공한다.
- computer 툴셋(computer_toolset_20260801)은 Messages API 전용이라 쓸 수 없다.
  대신 `computer` custom 도구가 행동 배열을 받아 같은 규칙으로 실행한다 (agent/batch.py).
- 보조 도구(list_ui_elements 등)는 같은 MCP 서버에 함께 올린다.
- Claude Code의 내장 도구(Bash, Read 등)는 모두 끄고, 우리 도구만 허용한다.
- 컨텍스트 관리는 Claude Code가 한다 (자동 압축). PC_AGENT_CONTEXT, 프롬프트 캐시 설정은 쓰이지 않는다.
- 인증: ANTHROPIC_API_KEY를 CLI에 넘기지 않으므로, 미리 `claude`를 실행해 구독 계정으로 로그인해 둬야 한다.
"""
import asyncio
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    tool,
)

import config
from actions import backends
from actions.assist import TOOL_DEFS as ASSIST_TOOL_DEFS, AssistTools
from actions.executor import Executor
from agent import batch
from agent.loop import RunResult, build_system_prompt
from logs.recorder import Recorder

SERVER = "pc"

SDK_PROMPT_NOTE = """
도구 사용법:
- 마우스/키보드 조작은 computer 도구 하나로 합니다. 이어서 할 행동은 actions 배열에 한 번에 담으세요.
- 배치가 screenshot/zoom으로 끝나지 않으면 실행 후 화면이 자동으로 붙으므로 따로 screenshot을 넣지 않아도 됩니다.
"""


def tool_name(name: str) -> str:
    return f"mcp__{SERVER}__{name}"


def map_status(result: ResultMessage) -> str:
    if result.subtype == "error_max_turns":
        return "max_steps"
    if result.is_error or result.subtype != "success":
        return "error"
    if result.stop_reason == "max_tokens":
        return "truncated"
    return "done"


def apply_usage(stats: RunResult, usage: dict | None) -> None:
    u = usage or {}
    stats.input_tokens = u.get("input_tokens", 0) or 0
    stats.output_tokens = u.get("output_tokens", 0) or 0
    stats.cache_read_tokens = u.get("cache_read_input_tokens", 0) or 0
    stats.cache_write_tokens = u.get("cache_creation_input_tokens", 0) or 0


class _Tools:
    """MCP 도구 핸들러. 긴급 정지는 결과로 숨기지 않고 abort에 담아 루프가 멈추게 한다."""

    def __init__(self, executor: Executor, recorder: Recorder, stats: RunResult,
                 assist: AssistTools | None):
        self.executor = executor
        self.recorder = recorder
        self.stats = stats
        self.assist = assist
        self.abort: BaseException | None = None
        self.lock = asyncio.Lock()  # GUI 동작은 절대 겹쳐 실행하지 않는다

    def build(self) -> list:
        tools = [tool("computer", batch.COMPUTER_TOOL_DESCRIPTION, batch.COMPUTER_TOOL_SCHEMA)(self.computer)]
        for name in (self.assist.names if self.assist else []):
            d = ASSIST_TOOL_DEFS[name]
            tools.append(tool(name, d["description"], d["input_schema"])(self._assist_handler(name)))
        return tools

    def _stopped(self) -> dict | None:
        if self.abort is not None:
            return {"content": [{"type": "text", "text": "긴급 정지되었습니다."}], "is_error": True}
        return None

    async def computer(self, args: dict[str, Any]) -> dict:
        async with self.lock:
            if (stopped := self._stopped()) is not None:
                return stopped
            try:
                # 동기로 실행한다: Guard의 y/n 확인(input)이 메인 스레드에서 돌아야 하므로
                out = batch.run_batch(args["actions"], self.executor, self.recorder, config.AUTO_SCREENSHOT)
            except Exception as err:
                if not backends.is_failsafe(err):
                    raise
                self.abort = err
                return self._stopped()
            self.stats.actions += out.executed
            self.stats.action_errors += out.errors
            return {"content": out.content, "is_error": out.is_error}

    def _assist_handler(self, name: str):
        async def handler(args: dict[str, Any]) -> dict:
            async with self.lock:
                if (stopped := self._stopped()) is not None:
                    return stopped
                print(f"  → {name} {args}")
                self.stats.actions += 1
                try:
                    result = self.assist.run(name, args)
                except Exception as err:
                    if backends.is_failsafe(err):
                        self.abort = err
                        return self._stopped()
                    self.stats.action_errors += 1
                    print(f"  ✗ {err}")
                    self.recorder.event("action", name=name, input=args, ok=False, error=str(err))
                    return {"content": [{"type": "text", "text": f"오류: {err}"}], "is_error": True}
                self.recorder.event("action", name=name, input=args, ok=True)
                return {"content": batch.to_mcp_content(result)}
        return handler


async def _run(goal: str, executor: Executor, recorder: Recorder, stats: RunResult) -> RunResult:
    assist = AssistTools(executor, config.ASSIST) if config.ASSIST else None
    handlers = _Tools(executor, recorder, stats, assist)
    tools = handlers.build()
    allowed = [tool_name(t.name) for t in tools]

    options = ClaudeAgentOptions(
        model=config.MODEL,
        system_prompt=build_system_prompt(assist) + SDK_PROMPT_NOTE,
        tools=[],                      # 내장 도구(Bash, Read, Edit 등) 전부 끄기
        mcp_servers={SERVER: create_sdk_mcp_server(SERVER, tools=tools)},
        allowed_tools=allowed,
        permission_mode="dontAsk",     # 허용 목록 밖의 도구는 묻지 않고 거부
        setting_sources=[],            # 사용자/프로젝트 설정, CLAUDE.md를 읽지 않음 (실험 격리)
        max_turns=config.MAX_STEPS,
        # API 키가 있으면 CLI가 API로 과금하므로 비워서 구독 로그인을 쓰게 한다
        env={"ANTHROPIC_API_KEY": ""},
    )
    recorder.event("engine", engine="sdk", model=config.MODEL, tools=allowed)

    async def prompt():
        # 지시 텍스트를 이미지보다 먼저 둔다 (API 엔진과 같은 순서)
        yield {
            "type": "user",
            "message": {"role": "user", "content": [
                {"type": "text", "text": f"목표: {goal}\n\n아래는 현재 화면입니다."},
                executor.screenshot_block("initial"),
            ]},
            "parent_tool_use_id": None,
        }

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt())
        seen: set[str] = set()  # CLI는 응답 하나를 블록마다 나눠 보내므로 message_id로 단계를 센다
        async for msg in client.receive_response():
            if handlers.abort is not None:
                await client.interrupt()
                raise handlers.abort
            if isinstance(msg, AssistantMessage):
                if msg.parent_tool_use_id is None and msg.message_id and msg.message_id not in seen:
                    seen.add(msg.message_id)
                    stats.steps = len(seen)
                    print(f"\n[step {stats.steps}/{config.MAX_STEPS}]")
                    recorder.event("response", step=stats.steps, stop_reason=msg.stop_reason, usage=msg.usage)
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text.strip():
                        print(f"  Claude: {block.text.strip()}")
                    elif isinstance(block, ToolUseBlock) and not block.name.startswith(f"mcp__{SERVER}__"):
                        print(f"  (허용되지 않은 도구 요청: {block.name})")
            elif isinstance(msg, ResultMessage):
                apply_usage(stats, msg.usage)
                stats.steps = msg.num_turns or stats.steps
                stats.stop_reason = msg.stop_reason
                stats.status = map_status(msg)
                if stats.status == "max_steps":
                    stats.final = f"최대 단계 수({config.MAX_STEPS})에 도달해 중단했습니다."
                elif stats.status == "error":
                    stats.final = "; ".join(msg.errors or []) or (msg.result or "알 수 없는 오류")
                else:
                    stats.final = (msg.result or "").strip() or "(완료 보고 없음)"
                recorder.event("done", step=stats.steps, status=stats.status, final=stats.final,
                               cost_usd=msg.total_cost_usd, usage=msg.usage)
        if handlers.abort is not None:
            raise handlers.abort
    return stats


def run(goal: str, executor: Executor, recorder: Recorder, stats: RunResult | None = None) -> RunResult:
    """agent.loop.run과 같은 형태. stats를 넘기면 중간에 멈춰도 그때까지의 통계가 남는다."""
    stats = stats if stats is not None else RunResult()
    return asyncio.run(_run(goal, executor, recorder, stats))
