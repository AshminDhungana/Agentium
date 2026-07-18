"""
Integration test for the remote_exec tool. Requires a working Docker daemon
with the `python:3.11-slim` image available. Skipped automatically when Docker
is unavailable (mirrors test_execution_wait.py).
"""
import os
import pytest

docker_available = False
try:
    import docker
    client = docker.DockerClient(base_url=os.getenv("HOST_DOCKER_SOCKET", "/var/run/docker.sock"))
    client.ping()
    docker_available = True
except Exception:
    docker_available = False

pytestmark = pytest.mark.skipif(not docker_available, reason="Docker daemon not available")


@pytest.mark.asyncio
async def test_remote_exec_filesystem_write_in_sandbox():
    from backend.tools.remote_exec_tool import execute
    code = (
        "import os\n"
        "with open('/tmp/sandbox_note.txt', 'w') as f:\n"
        "    f.write('hello-from-sandbox')\n"
        "result = os.path.exists('/tmp/sandbox_note.txt')\n"
    )
    res = await execute(agent_id="30001", code=code)
    assert res["status"] == "completed"
    assert res["summary"]["output_schema"] == {"type": "bool"}


@pytest.mark.asyncio
async def test_remote_exec_network_blocked_by_default():
    from backend.tools.remote_exec_tool import execute
    code = (
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('https://example.com', timeout=5)\n"
        "    result = 'network_ok'\n"
        "except Exception as e:\n"
        "    result = f'blocked: {type(e).__name__}'\n"
    )
    res = await execute(agent_id="30001", code=code, network_access=False)
    # default deny: must NOT reach the internet
    assert res["status"] == "completed"
    assert "blocked" in str(res["summary"]["sample"]).lower() or "blocked" in str(res["summary"].get("stdout", "")).lower()


@pytest.mark.asyncio
async def test_remote_exec_network_allowed_optin():
    from backend.tools.remote_exec_tool import execute
    code = (
        "import urllib.request\n"
        "try:\n"
        "    r = urllib.request.urlopen('https://example.com', timeout=10)\n"
        "    result = r.status\n"
        "except Exception as e:\n"
        "    result = f'err: {type(e).__name__}'\n"
    )
    res = await execute(agent_id="30001", code=code, network_access=True)
    assert res["status"] == "completed"
    # with opt-in bridge, the public fetch succeeds
    assert res["summary"]["output_schema"] == {"type": "int"} or "err" not in str(res["summary"].get("sample", ""))


@pytest.mark.asyncio
async def test_remote_exec_pii_isolation():
    from backend.tools.remote_exec_tool import execute
    # 1000-row "secret" DataFrame; only schema + <=3 sample rows may return
    code = (
        "import pandas as pd\n"
        "df = pd.DataFrame({'secret': [f'TOPSECRET-{i}' for i in range(1000)]})\n"
        "result = df\n"
    )
    res = await execute(
        agent_id="30001",
        code=code,
        dependencies=["pandas"],
    )
    assert res["status"] == "completed"
    summary = res["summary"]
    assert summary["row_count"] == 1000
    # at most 3 sample rows escape the sandbox
    assert len(summary["sample"]) <= 3
    # the full 1000-row payload must NOT be present anywhere in the result
    blob = str(res)
    assert "TOPSECRET-999" not in blob
    assert "TOPSECRET-500" not in blob
