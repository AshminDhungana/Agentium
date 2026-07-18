import os
from backend.tools import desktop_tool


def test_create_file_resolves_relative(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop_tool.host_path, "HOST_HOME_MOUNT", str(tmp_path))
    monkeypatch.setenv("AGENTIUM_WORKSPACE_ROOT", str(tmp_path))
    from backend.tools._workspace import agent_workspace_path
    res = desktop_tool.FileManagementTool().create_file("notes.txt", "hi", agent_id="30001")
    expected = os.path.join(agent_workspace_path("30001"), "notes.txt")
    assert res["status"] == "success"
    assert os.path.normpath(res["path"]) == os.path.normpath(expected)
    assert os.path.isfile(expected)
