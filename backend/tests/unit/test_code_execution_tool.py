# backend/tests/unit/test_code_execution_tool.py
import asyncio
from types import SimpleNamespace
from backend.tools import code_execution_tool


def test_execute_calls_service(monkeypatch):
    calls = {}

    class FakeService:
        async def execute(self, **kw):
            calls.update(kw)
            return {"status": "success", "summary": "ok", "execution_time_ms": 1}

    monkeypatch.setattr(code_execution_tool, "_make_service", lambda: FakeService())
    result = asyncio.get_event_loop().run_until_complete(
        code_execution_tool.execute(
            "execute", code="print(1)", agent_id="00001", language="python"
        )
    )
    assert result["status"] == "success"
    assert calls["code"] == "print(1)"
    assert calls["agent_id"] == "00001"
    assert calls["language"] == "python"


def test_blocked_code_returns_error(monkeypatch):
    class FakeService:
        async def execute(self, **kw):
            return {"status": "blocked", "error": "forbidden syscall", "security_result": {"passed": False}}

    monkeypatch.setattr(code_execution_tool, "_make_service", lambda: FakeService())
    result = asyncio.get_event_loop().run_until_complete(
        code_execution_tool.execute("execute", code="import os; os.system('x')", agent_id="00001")
    )
    assert result["status"] == "blocked"


def test_help_action():
    result = asyncio.get_event_loop().run_until_complete(code_execution_tool.execute("help"))
    assert result["status"] == "success"
    assert "sandbox" in result["description"].lower()
