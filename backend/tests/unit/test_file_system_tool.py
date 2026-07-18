# backend/tests/unit/test_file_system_tool.py
from backend.tools.file_tool import FileSystemTool


def _write(tmp_path, name, text):
    p = tmp_path / name
    if isinstance(text, bytes):
        p.write_bytes(text)
    else:
        p.write_text(text, encoding="utf-8")
    return str(p)


def test_read_whole_file_legacy_shape(tmp_path):
    tool = FileSystemTool()
    path = _write(tmp_path, "f.txt", "a\nb\nc\n")
    res = tool.read_file(path)
    assert res["status"] == "success"
    assert res["content"] == "a\nb\nc\n"
    assert res["size"] == 6
    assert res["truncated"] is False
    assert res["total_lines"] == 3
    # legacy mode returns raw content, NOT numbered
    assert "\t" not in res["content"]


def test_read_precise_slice_is_numbered(tmp_path):
    tool = FileSystemTool()
    text = "\n".join(f"line{n}" for n in range(1, 11)) + "\n"
    path = _write(tmp_path, "f.txt", text)
    res = tool.read_file(path, offset=2, limit=3)
    assert res["status"] == "success"
    assert res["total_lines"] == 10
    lines = res["content"].split("\n")
    # numbered format "%6d\t" — line 2..4
    assert lines[0] == "     2\tline2"
    assert lines[1] == "     3\tline3"
    assert lines[2] == "     4\tline4"


def test_read_offset_out_of_range(tmp_path):
    tool = FileSystemTool()
    path = _write(tmp_path, "f.txt", "a\nb\n")
    res = tool.read_file(path, offset=99)
    assert res["status"] == "error"
    assert "out of range" in res["error"]


def test_read_binary_is_rejected(tmp_path):
    tool = FileSystemTool()
    path = _write(tmp_path, "f.bin", b"\x89PNG\r\n\x1a\n")  # PNG magic
    res = tool.read_file(path)
    assert res["status"] == "error"
    assert "binary file" in res["error"]
