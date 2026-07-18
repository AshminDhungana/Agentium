# backend/tests/unit/test_sandbox_workspace.py
from backend.services.remote_executor.sandbox import SandboxConfig, SandboxManager


class _FakeContainer:
    def __init__(self):
        self.id = "cid"
        self.name = "sandbox_test"


class _FakeContainers:
    def __init__(self):
        self.last_kwargs = None

    def run(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeContainer()


class _FakeDocker:
    def __init__(self):
        self.containers = _FakeContainers()

    def ping(self):
        return True


def test_config_defaults():
    cfg = SandboxConfig()
    assert cfg.workspace_enabled is False
    assert cfg.workspace_tmpfs_size_mb == 256


def test_workspace_tmpfs_added(monkeypatch):
    mgr = SandboxManager()
    mgr.docker_client = _FakeDocker()
    cfg = SandboxConfig(workspace_enabled=True, workspace_tmpfs_size_mb=128)
    import asyncio
    info = asyncio.get_event_loop().run_until_complete(
        mgr._create_raw_container("30001", cfg)
    )
    tmpfs = mgr.docker_client.containers.last_kwargs["tmpfs"]
    assert "/workspace" in tmpfs
    assert "size=128m" in tmpfs["/workspace"]
    assert "noexec" in tmpfs["/workspace"]
