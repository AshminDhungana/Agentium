import os
import json
import asyncio
from unittest.mock import AsyncMock, patch
from backend.services.remote_executor.service import RemoteExecutorService
from backend.tools._workspace import ensure_agent_workspace, host_visible_path
from backend.core.security.execution_guard import SecurityCheckResult


def test_execute_returns_workspace_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ENABLED", "true")

    # Simulate docker cp: materialize a file in the host workspace dir only for
    # the workspace copy-out command (source ends with /workspace/.).
    captured = {}

    def fake_run(cmd, *a, **k):
        class R:
            returncode = 0
            stderr = b""
            stdout = b"{}"
        if cmd[:2] == ["docker", "cp"] and cmd[2].endswith("/workspace/."):
            captured["dst"] = cmd[3]
            os.makedirs(captured["dst"], exist_ok=True)
            with open(os.path.join(captured["dst"], "result.txt"), "w") as f:
                f.write("hello")
        elif cmd[:2] == ["docker", "exec"]:
            # Synthesize a successful in-container execution result.
            R.stdout = json.dumps({
                "success": True,
                "output_schema": {},
                "row_count": 0,
                "sample": [],
                "stats": {},
                "stdout": "",
                "stderr": "",
                "execution_time_ms": 1,
            }).encode()
        return R()

    svc = RemoteExecutorService(db_session=None)
    svc.sandbox_manager.create_sandbox = AsyncMock(return_value={"sandbox_id": "sb1", "container_id": "c1"})
    svc.sandbox_manager.destroy_sandbox = AsyncMock(return_value=True)
    # Bypass the security guard so the workspace-persistence path is exercised.
    svc.guard.validate_code = lambda code, tier: SecurityCheckResult(
        passed=True, violations=[], severity="none"
    )

    with patch("backend.services.remote_executor.service.subprocess.run", side_effect=fake_run):
        result = asyncio.get_event_loop().run_until_complete(
            svc.execute(code="open('result.txt','w').write('hello')", agent_id="30001", task_id="t9")
        )

    assert result["status"] == "completed"
    assert result["workspace_path"] == host_visible_path(ensure_agent_workspace("30001", "t9"))
    assert any(a["name"] == "result.txt" for a in result["artifacts"])
