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


class _FakeVolume:
    def __init__(self):
        self.id = "vol_id"
        self.name = "agentium_workspace_test"
        self.attrs = {}

class _FakeVolumes:
    def create(self, **kwargs):
        return _FakeVolume()

class _FakeDocker:
    def __init__(self):
        self.containers = _FakeContainers()
        self.volumes = _FakeVolumes()

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
    volumes = mgr.docker_client.containers.last_kwargs.get("volumes", {})
    assert any("workspace" in k for k in volumes)
