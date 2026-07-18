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


def test_read_total_lines_no_trailing_newline(tmp_path):
    tool = FileSystemTool()
    path = _write(tmp_path, "f.txt", "a\nb\nc")
    res = tool.read_file(path)
    assert res["status"] == "success"
    assert res["total_lines"] == 3
    assert res["content"] == "a\nb\nc"
    assert res["truncated"] is False


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
    assert res["truncated"] is True


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


def test_replace_single_line(tmp_path):
    tool = FileSystemTool()
    path = _write(tmp_path, "f.txt", "a\nb\nc\n")
    res = tool.replace_lines(path, 2, 2, "B")
    assert res["status"] == "success"
    assert res["lines_replaced"] == 1
    assert pathlib_read(tmp_path, "f.txt") == "a\nB\nc\n"


def test_replace_range_multiline(tmp_path):
    tool = FileSystemTool()
    path = _write(tmp_path, "f.txt", "a\nb\nc\nd\n")
    res = tool.replace_lines(path, 2, 3, "X\nY")
    assert res["status"] == "success"
    assert pathlib_read(tmp_path, "f.txt") == "a\nX\nY\nd\n"


def test_replace_last_line(tmp_path):
    tool = FileSystemTool()
    path = _write(tmp_path, "f.txt", "a\nb\nc\n")
    res = tool.replace_lines(path, 3, 3, "Z")
    assert res["status"] == "success"
    assert pathlib_read(tmp_path, "f.txt") == "a\nb\nZ\n"


def test_replace_lines_fails_loudly_start_gt_end(tmp_path):
    tool = FileSystemTool()
    path = _write(tmp_path, "f.txt", "a\nb\nc\n")
    before = pathlib_read(tmp_path, "f.txt")
    res = tool.replace_lines(path, 3, 2, "X")
    assert res["status"] == "error"
    assert pathlib_read(tmp_path, "f.txt") == before  # no change


def test_replace_lines_fails_loudly_out_of_range(tmp_path):
    tool = FileSystemTool()
    path = _write(tmp_path, "f.txt", "a\nb\nc\n")
    before = pathlib_read(tmp_path, "f.txt")
    for bad in [(5, 5), (1, 9)]:
        res = tool.replace_lines(path, *bad, "X")
        assert res["status"] == "error"
        assert "out of range" in res["error"]
    assert pathlib_read(tmp_path, "f.txt") == before


def test_replace_lines_missing_file(tmp_path):
    tool = FileSystemTool()
    res = tool.replace_lines(str(tmp_path / "nope.txt"), 1, 1, "X")
    assert res["status"] == "error"


def test_replace_lines_backup_created(tmp_path):
    tool = FileSystemTool()
    path = _write(tmp_path, "f.txt", "a\nb\nc\n")
    res = tool.replace_lines(path, 2, 2, "B", backup=True)
    assert res["status"] == "success"
    assert (tmp_path / "f.txt.bak").exists()
    assert (tmp_path / "f.txt.bak").read_text() == "a\nb\nc\n"


def test_replace_lines_no_backup(tmp_path):
    tool = FileSystemTool()
    path = _write(tmp_path, "f.txt", "a\nb\nc\n")
    res = tool.replace_lines(path, 2, 2, "B", backup=False)
    assert res["status"] == "success"
    assert not (tmp_path / "f.txt.bak").exists()


def pathlib_read(tmp_path, name):
    return (tmp_path / name).read_text(encoding="utf-8")


def test_registry_exposes_replace_lines():
    from backend.core.tool_registry import ToolRegistry
    from backend.tools.file_tool import FileSystemTool

    reg = ToolRegistry()
    reg._initialize_tools()

    expected = FileSystemTool.replace_lines
    tool = reg.get_tool("replace_lines")
    assert tool is not None
    assert callable(tool["function"])
    assert tool["function"].__func__ is expected
    for key in ("filepath", "start_line", "end_line", "content"):
        assert key in tool["parameters"]
    assert "0xxxx" in tool["authorized_tiers"]
    assert "9xxxx" in tool["authorized_tiers"]
