import os
import json
import io
import tarfile
import asyncio
from unittest.mock import AsyncMock
from backend.services.remote_executor.service import RemoteExecutorService
from backend.tools._workspace import ensure_agent_workspace, host_visible_path
from backend.core.security.execution_guard import SecurityCheckResult


def _make_tar(name: str, content: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name=name)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content.encode()))
    return buf.getvalue()


class _FakeExecResult:
    def __init__(self, exit_code=0, output=b""):
        self.exit_code = exit_code
        self.output = output


class _FakeContainer:
    id = "c1"
    name = "sb1"

    def exec_run(self, cmd, **kwargs):
        return _FakeExecResult(
            exit_code=0,
            output=json.dumps({
                "success": True,
                "output_schema": {},
                "row_count": 0,
                "sample": [],
                "stats": {},
                "stdout": "",
                "stderr": "",
                "execution_time_ms": 1,
            }).encode(),
        )

    def put_archive(self, path, data):
        pass

    def get_archive(self, path):
        return (
            [_make_tar("result.txt", "hello")],
            {"name": "workspace"},
        )


class _FakeContainers:
    def get(self, container_id):
        return _FakeContainer()


class _FakeDocker:
    def __init__(self):
        self.containers = _FakeContainers()

    def ping(self):
        return True


def test_execute_returns_workspace_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ENABLED", "true")

    svc = RemoteExecutorService(db_session=None)
    svc.sandbox_manager.create_sandbox = AsyncMock(return_value={"sandbox_id": "sb1", "container_id": "c1"})
    svc.sandbox_manager.destroy_sandbox = AsyncMock(return_value=True)
    svc.sandbox_manager.docker_client = _FakeDocker()
    # Bypass the security guard so the workspace-persistence path is exercised.
    svc.guard.validate_code = lambda code, tier: SecurityCheckResult(
        passed=True, violations=[], severity="none"
    )

    result = asyncio.get_event_loop().run_until_complete(
        svc.execute(code="open('result.txt','w').write('hello')", agent_id="30001", task_id="t9")
    )

    assert result["status"] == "completed"
    assert result["workspace_path"] == host_visible_path(ensure_agent_workspace("30001", "t9"))
    assert any(a["name"] == "result.txt" for a in result["artifacts"])
