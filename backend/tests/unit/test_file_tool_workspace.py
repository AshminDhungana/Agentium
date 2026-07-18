import os
from backend.tools.file_tool import FileSystemTool


def test_write_file_resolves_relative(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", str(tmp_path))
    tool = FileSystemTool()
    res = tool.write_file("hello.txt", "data", agent_id="30001")
    assert res["status"] == "success"
    expected = os.path.join(str(tmp_path), "30001", "hello.txt")
    # resolve_in_workspace joins with forward slashes (container contract);
    # normalise so the assertion is OS-separator agnostic.
    assert os.path.normpath(res["path"]) == os.path.normpath(expected)
    assert os.path.isfile(expected)


def test_write_file_absolute_host_passthrough(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", str(tmp_path))
    tool = FileSystemTool()
    # An explicitly absolute path (recognised as absolute by resolve_in_workspace,
    # which treats /-prefixed paths as container-local passthrough) is NOT
    # remapped into the agent workspace.
    target = "/tmp/explicit/x.txt"
    res = tool.write_file(target, "data", agent_id="30001")
    assert res["path"] == target


def test_get_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", str(tmp_path))
    tool = FileSystemTool()
    res = tool.get_workspace(agent_id="30001")
    assert res["status"] == "success"
    assert res["path"].endswith("30001")
