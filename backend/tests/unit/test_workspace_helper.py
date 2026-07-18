# backend/tests/unit/test_workspace_helper.py
import os
from backend.tools import _workspace as w


def test_agent_workspace_path(monkeypatch):
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", "/host_home/agentium-workspace")
    assert w.agent_workspace_path("30001") == "/host_home/agentium-workspace/30001"


def test_resolve_relative_goes_to_workspace(monkeypatch):
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", "/host_home/agentium-workspace")
    got = w.resolve_in_workspace("output.html", "30001")
    assert got == "/host_home/agentium-workspace/30001/output.html"


def test_resolve_absolute_host_passthrough(monkeypatch):
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", "/host_home/agentium-workspace")
    assert w.resolve_in_workspace("/host_home/x/y.txt", "30001") == "/host_home/x/y.txt"
    assert w.resolve_in_workspace("/host/else/z.txt", "30001") == "/host/else/z.txt"


def test_resolve_tmp_stays_container_local(monkeypatch):
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", "/host_home/agentium-workspace")
    assert w.resolve_in_workspace("/tmp/inner.txt", "30001") == "/tmp/inner.txt"


def test_ensure_creates_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", str(tmp_path))
    path = w.ensure_agent_workspace("30001", "task-9")
    assert path.endswith("30001/task-9")
    assert os.path.isdir(path)


def test_host_visible_shortens_home(monkeypatch):
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", "/host_home/agentium-workspace")
    visible = w.host_visible_path("/host_home/agentium-workspace/30001/task-9")
    assert visible == "~/agentium-workspace/30001/task-9"


def test_manifest_lists_files(tmp_path):
    (tmp_path / "a.txt").write_text("hi")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("yo")
    items = w._manifest(str(tmp_path))
    names = {i["name"] for i in items}
    assert names == {"a.txt", "sub/b.txt"}


def test_resolve_disabled_returns_unchanged(monkeypatch):
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ENABLED", "false")
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", "/host_home/agentium-workspace")
    assert w.resolve_in_workspace("output.html", "30001") == "output.html"


def test_resolve_host_slash_prefix_passthrough(monkeypatch):
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", "/host_home/agentium-workspace")
    assert w.resolve_in_workspace("/host/x.txt", "30001") == "/host/x.txt"
    assert w.resolve_in_workspace("/host_home/x.txt", "30001") == "/host_home/x.txt"


def test_validate_config_ok_under_host(monkeypatch, caplog):
    import logging
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", "/host_home/agentium-workspace")
    caplog.set_level(logging.WARNING)
    assert w.validate_workspace_config() is True
    assert not any("not under /host" in r.message for r in caplog.records)


def test_validate_config_warns_when_not_under_host(monkeypatch, caplog):
    import logging
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", "/var/lib/agentium")
    caplog.set_level(logging.WARNING)
    assert w.validate_workspace_config() is False
    assert any("not under /host" in r.message for r in caplog.records)
