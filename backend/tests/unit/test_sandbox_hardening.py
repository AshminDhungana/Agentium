# backend/tests/unit/test_sandbox_hardening.py
import pytest
from backend.services.remote_executor.sandbox import SandboxConfig, SandboxManager


def test_sandbox_config_defaults_are_safe():
    cfg = SandboxConfig()
    # default network is OFF
    assert cfg.network_mode == "none"
    assert cfg.max_disk_mb == 1024


def test_create_raw_container_sets_readonly_and_tmpfs(monkeypatch):
    mgr = SandboxManager()
    # stub the docker client so no real container is created
    class FakeContainer:
        id = "cid123"
    captured = {}

    class FakeContainers:
        def run(self, **kwargs):
            captured.update(kwargs)
            return FakeContainer()

    class FakeDocker:
        def __init__(self):
            self.containers = FakeContainers()

        def ping(self):
            return True

    monkeypatch.setattr(mgr, "docker_client", FakeDocker())

    import asyncio
    cfg = SandboxConfig()
    asyncio.get_event_loop().run_until_complete(mgr._create_raw_container("30001", cfg))

    assert captured.get("read_only") is True
    assert "/tmp" in (captured.get("tmpfs") or {})
    # tmpfs must be noexec/nosuid/nodev and size-capped
    tmpfs_opts = captured["tmpfs"]["/tmp"]
    assert "noexec" in tmpfs_opts and "nosuid" in tmpfs_opts and "nodev" in tmpfs_opts
    assert "size=" in tmpfs_opts
    # network off by default
    assert captured.get("network_mode") == "none"
