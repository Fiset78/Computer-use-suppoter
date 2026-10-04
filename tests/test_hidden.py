"""Claude Code CLI를 띄울 때 콘솔 창 숨김 플래그가 붙는지 (Windows 흉내)."""
import asyncio

import anyio

from agent import hidden


def test_noop_off_windows(monkeypatch):
    monkeypatch.setattr(hidden, "_installed", False)
    before = anyio.open_process
    assert hidden.hide_child_consoles("linux") is False
    assert anyio.open_process is before


def test_adds_create_no_window(monkeypatch):
    seen = {}

    async def fake_open_process(cmd, **kwargs):
        seen.update(kwargs)
        return "proc"

    monkeypatch.setattr(hidden, "_installed", False)
    monkeypatch.setattr(anyio, "open_process", fake_open_process)
    assert hidden.hide_child_consoles("win32") is True
    assert hidden.hide_child_consoles("win32") is True  # 두 번 불러도 한 번만 감싼다
    result = asyncio.run(anyio.open_process(["claude"], stdin=None, creationflags=0x10))
    assert result == "proc"
    assert seen["creationflags"] == 0x10 | hidden.CREATE_NO_WINDOW
