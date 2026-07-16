# backend/tests/unit/test_desktop_host_access.py
from backend.tools.desktop_tool import FileManagementTool


def test_file_tool_passthrough_host_home():
    t = FileManagementTool()
    assert t._host_path("/host_home/Desktop/a.txt") == "/host_home/Desktop/a.txt"


def test_file_tool_tilde_expands():
    t = FileManagementTool()
    assert t._host_path("~/Desktop/a.txt") == "/host_home/Desktop/a.txt"


import backend.tools.desktop_tool as desktop_tool
from backend.tools.desktop_tool import DocumentTool


def test_create_document_writes_to_host_home(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop_tool.host_path, "HOST_HOME_MOUNT", str(tmp_path))
    monkeypatch.setattr(desktop_tool.host_path, "HOST_FS_MOUNT", str(tmp_path / "fs"))
    tool = DocumentTool()
    target = str(tmp_path / "Desktop" / "memo.md")
    res = tool.create_document(target, content="# Hello")
    assert res["status"] == "success"
    assert (tmp_path / "Desktop" / "memo.md").read_text().startswith("# Hello")


def test_read_document_reads_from_host_home(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop_tool.host_path, "HOST_HOME_MOUNT", str(tmp_path))
    monkeypatch.setattr(desktop_tool.host_path, "HOST_FS_MOUNT", str(tmp_path / "fs"))
    (tmp_path / "Desktop").mkdir()
    (tmp_path / "Desktop" / "note.md").write_text("body text")
    tool = DocumentTool()
    res = tool.read_document(str(tmp_path / "Desktop" / "note.md"))
    assert res["status"] == "success"
    assert res["content"] == "body text"
