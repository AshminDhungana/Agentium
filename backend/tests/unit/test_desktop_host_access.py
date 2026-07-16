# backend/tests/unit/test_desktop_host_access.py
from backend.tools.desktop_tool import FileManagementTool


def test_file_tool_passthrough_host_home():
    t = FileManagementTool()
    assert t._host_path("/host_home/Desktop/a.txt") == "/host_home/Desktop/a.txt"


def test_file_tool_tilde_expands():
    t = FileManagementTool()
    assert t._host_path("~/Desktop/a.txt") == "/host_home/Desktop/a.txt"
