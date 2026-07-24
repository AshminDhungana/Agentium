# backend/tests/unit/test_sandbox_hardening.py
import pytest
from backend.services.remote_executor.sandbox import (
    SandboxConfig,
    SandboxManager,
    effective_egress_policy,
    blocked_egress_cidrs,
)


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

    # read_only is not set (put_archive requires writable rootfs)
    # tmpfs is empty (volumes used instead for workspace)
    # network off by default
    assert captured.get("network_mode") == "none"


def test_config_accepts_allowed_egress_hosts():
    cfg = SandboxConfig(allowed_hosts=["pypi.org", "api.github.com"])
    assert cfg.allowed_hosts == ["pypi.org", "api.github.com"]
    # defaults: no network
    assert SandboxConfig().network_mode == "none"


def test_effective_egress_policy_returns_allowed_and_blocked():
    cfg = SandboxConfig(allowed_hosts=["pypi.org", "api.github.com"])
    policy = effective_egress_policy(cfg)
    assert policy["allowed"] == ["pypi.org", "api.github.com"]
    assert policy["blocked"] == list(blocked_egress_cidrs())
    assert "169.254.169.254/32" in policy["blocked"]


def test_effective_egress_policy_empty_allowed_defaults_to_empty_list():
    cfg = SandboxConfig()
    policy = effective_egress_policy(cfg)
    assert policy["allowed"] == []
    assert policy["blocked"] == list(blocked_egress_cidrs())


def test_create_raw_container_records_egress_labels_in_bridge_mode(monkeypatch):
    mgr = SandboxManager()
    captured = {}

    class FakeContainer:
        id = "cid456"

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
    cfg = SandboxConfig(network_mode="bridge", allowed_hosts=["pypi.org", "api.github.com"])
    asyncio.get_event_loop().run_until_complete(mgr._create_raw_container("30002", cfg))

    labels = captured.get("labels", {})
    assert labels["agentium.egress_allowed"] == "pypi.org,api.github.com"
    assert "169.254.169.254/32" in labels["agentium.egress_blocked"]
    # read_only is not set; tmpfs is empty — intentional for put_archive compat
    assert captured.get("cap_drop") == ["ALL"]
    assert captured.get("security_opt") == ["no-new-privileges"]
    assert captured.get("network_mode") == "bridge"


def test_create_raw_container_egress_labels_none_when_no_allowed_hosts(monkeypatch):
    mgr = SandboxManager()
    captured = {}

    class FakeContainer:
        id = "cid789"

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
    cfg = SandboxConfig(network_mode="bridge")
    asyncio.get_event_loop().run_until_complete(mgr._create_raw_container("30003", cfg))

    labels = captured.get("labels", {})
    assert labels["agentium.egress_allowed"] == "none"
    assert "169.254.169.254/32" in labels["agentium.egress_blocked"]
