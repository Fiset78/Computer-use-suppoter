"""엔진 선택. 엔진별 의존성(anthropic / claude_agent_sdk)은 고를 때만 import한다."""
import config


def get_runner(engine: str):
    """engine 이름 → (run 함수, 해당 엔진의 API 오류 예외 클래스)."""
    if engine == "sdk":
        from claude_agent_sdk import ClaudeSDKError

        from agent import sdk_loop
        return sdk_loop.run, ClaudeSDKError
    if engine == "api":
        from anthropic import APIError

        from agent import loop
        return loop.run, APIError
    raise ValueError(f"알 수 없는 엔진: {engine} (사용 가능: {', '.join(config.ENGINES)})")
