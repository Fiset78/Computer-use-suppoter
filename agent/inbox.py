"""실행 중 추가 지시함. 실행 창에서 실행 도중 말하거나 입력한 지시를 모아 두었다가,
엔진이 다음 도구 결과에 붙여 Claude에게 바로 전달한다. 실행이 끝날 때까지 전달되지 못한 지시는
실행 창이 다음 실행의 목표로 이어서 쓴다. 스레드 사이에서 쓰므로 잠금을 건다 (순수 모듈).
"""
import re
import threading

# 도구 결과에서 이 표시로 시작하는 글만 사용자 지시다 (화면에 보이는 글과 구분)
MARKER = "[pc-agent: 사용자가 실행 중에 보낸 추가 지시]"

# 이 말만 했으면 지시 대신 정지로 처리한다
STOP_WORDS = ("멈춰", "멈춰줘", "정지", "정지해", "정지해줘", "그만", "그만해", "그만해줘", "중지", "중지해", "스톱", "stop")


def is_stop_command(text: str) -> bool:
    t = re.sub(r"[\s.!?,~]+", "", (text or "").lower())
    return t in STOP_WORDS


class Inbox:
    def __init__(self):
        self._items: list[str] = []
        self._lock = threading.Lock()

    def put(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            with self._lock:
                self._items.append(text)

    def drain(self) -> list[str]:
        with self._lock:
            items, self._items = self._items, []
        return items

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


def as_block(messages: list[str]) -> dict:
    """도구 결과에 붙일 텍스트 블록."""
    body = "\n".join(f"- {m}" for m in messages)
    return {"type": "text", "text": f"{MARKER}\n{body}\n이 지시를 지금 하던 일보다 우선해서 반영하세요."}


def follow_up_goal(previous_goal: str, previous_result: str, messages: list[str]) -> str:
    """실행이 끝난 뒤 남은 지시로 이어서 실행할 목표."""
    body = "\n".join(f"- {m}" for m in messages)
    return (f"방금 실행이 끝난 직후 사용자가 추가 지시를 보냈습니다. 화면을 확인하고 이어서 하세요.\n\n"
            f"직전 목표:\n{previous_goal}\n\n직전 결과:\n{previous_result or '(없음)'}\n\n추가 지시:\n{body}")


inbox = Inbox()  # 프로세스에 하나 (실행 창이 넣고 엔진이 꺼낸다)
