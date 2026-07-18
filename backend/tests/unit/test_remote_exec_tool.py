# backend/tests/unit/test_remote_exec_tool.py
import pytest
from unittest.mock import AsyncMock, patch
from backend.tools import remote_exec_tool


def _fake_service_result():
    return {
        "execution_id": "exec_test123",
        "status": "completed",
        "summary": {
            "output_schema": {"name": "object", "age": "int64"},
            "row_count": 1000,
            "sample": [{"name": "Alice", "age": 25}],  # only 1 sample row
            "stats": {"age": {"mean": 30.0}},
            "stdout": "ok",
            "stderr": "",
            "execution_time_ms": 12,
            "error_message": None,
            "success": True,
        },
        "error": None,
        "security_result": {"passed": True, "violations": [], "severity": "none", "recommendation": None},
        "started_at": "2026-07-18T00:00:00",
        "completed_at": "2026-07-18T00:00:01",
        "execution_time_ms": 12,
    }


@pytest.mark.asyncio
async def test_remote_exec_returns_summary_only():
    with patch.object(remote_exec_tool.RemoteExecutorService, "execute", new=AsyncMock(return_value=_fake_service_result())):
        result = await remote_exec_tool.execute(
            agent_id="30001",
            code="result = {'name':['Alice'],'age':[25]}",
            input_data={"x": 1},
        )
    assert result["status"] == "completed"
    assert result["summary"]["row_count"] == 1000
    # raw data never escapes: only schema/stats/sample, never the full payload
    assert "raw" not in result
    assert len(result["summary"]["sample"]) <= 3


@pytest.mark.asyncio
async def test_remote_exec_passes_real_agent_id():
    captured = {}

    async def _capture(self, **kwargs):
        captured.update(kwargs)
        return _fake_service_result()

    with patch.object(remote_exec_tool.RemoteExecutorService, "execute", new=_capture):
        await remote_exec_tool.execute(agent_id="30001", code="print('hi')")
    # real agent id is forwarded, NOT the hardcoded "00001"
    assert captured["agent_id"] == "30001"
    assert captured["code"] == "print('hi')"
    assert captured["network_access"] is False
