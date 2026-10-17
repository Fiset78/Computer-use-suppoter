"""Windows에서 Claude Code CLI를 띄울 때 검은 콘솔 창이 뜨지 않게 한다.

실행 창(app.py)은 pythonw로 콘솔 없이 돈다. 이 상태에서 콘솔 프로그램(claude.exe)을 띄우면
Windows가 새 콘솔 창을 만들어 보여 준다. Agent SDK는 창 숨김 옵션을 주지 않으므로,
SDK가 쓰는 anyio.open_process에 CREATE_NO_WINDOW를 끼워 넣는다.
그 CLI가 다시 띄우는 프로그램도 창 없는 콘솔을 물려받아 창이 뜨지 않는다.
"""
import subprocess
import sys

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
_installed = False


def hide_child_consoles(platform: str = sys.platform) -> bool:
    """한 번만 설치한다. Windows가 아니면 아무것도 하지 않고 False."""
    global _installed
    if platform != "win32" or _installed:
        return _installed
    import anyio

    original = anyio.open_process

    async def open_process_hidden(*args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
        return await original(*args, **kwargs)

    anyio.open_process = open_process_hidden
    _installed = True
    return True
