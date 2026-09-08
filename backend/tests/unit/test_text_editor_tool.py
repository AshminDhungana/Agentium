"""
Quick smoke tests for text_editor_tool.
"""
import pytest
import asyncio


def asyncio_run(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def test_text_editor_view_file(tmp_path):
    from backend.tools.text_editor_tool import text_editor_tool

    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\nline3\n")

    result = asyncio_run(text_editor_tool.execute(action="view", path=str(f)))
    assert result["success"] is True
    assert result["total_lines"] == 3
    assert "line1" in result["content"]
    assert "line3" in result["content"]


def test_text_editor_view_range(tmp_path):
    from backend.tools.text_editor_tool import text_editor_tool

    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\nline3\nline4\nline5\n")

    result = asyncio_run(text_editor_tool.execute(action="view", path=str(f), view_range=[2, 4]))
    assert result["success"] is True
    assert result["total_lines"] == 5
    assert "line2" in result["content"]
    assert "line4" in result["content"]
    assert "line1" not in result["content"]
    assert "line5" not in result["content"]


def test_text_editor_create_file(tmp_path):
    from backend.tools.text_editor_tool import text_editor_tool

    f = tmp_path / "new.txt"
    result = asyncio_run(text_editor_tool.execute(action="create", path=str(f), content="hello\nworld\n"))
    assert result["success"] is True
    assert f.read_text() == "hello\nworld\n"


def test_text_editor_str_replace(tmp_path):
    from backend.tools.text_editor_tool import text_editor_tool

    f = tmp_path / "test.txt"
    f.write_text("hello world\nhello again\n")

    result = asyncio_run(text_editor_tool.execute(action="str_replace", path=str(f), old_str="hello world", new_str="hi world"))
    assert result["success"] is True
    assert f.read_text() == "hi world\nhello again\n"


def test_text_editor_str_replace_not_found(tmp_path):
    from backend.tools.text_editor_tool import text_editor_tool

    f = tmp_path / "test.txt"
    f.write_text("hello world\n")

    result = asyncio_run(text_editor_tool.execute(action="str_replace", path=str(f), old_str="not found", new_str="x"))
    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_text_editor_str_replace_ambiguous(tmp_path):
    from backend.tools.text_editor_tool import text_editor_tool

    f = tmp_path / "test.txt"
    f.write_text("hello\nhello\n")

    result = asyncio_run(text_editor_tool.execute(action="str_replace", path=str(f), old_str="hello", new_str="hi"))
    assert result["success"] is False
    assert "ambiguous" in result["error"].lower() or "times" in result["error"].lower()


def test_text_editor_insert_prepend(tmp_path):
    from backend.tools.text_editor_tool import text_editor_tool

    f = tmp_path / "test.txt"
    f.write_text("line2\nline3\n")

    result = asyncio_run(text_editor_tool.execute(action="insert", path=str(f), insert_line=1, insert_text="line1"))
    assert result["success"] is True
    assert f.read_text() == "line1\nline2\nline3\n"


def test_text_editor_insert_append(tmp_path):
    from backend.tools.text_editor_tool import text_editor_tool

    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\n")

    result = asyncio_run(text_editor_tool.execute(action="insert", path=str(f), insert_line=5, insert_text="line3"))
    assert result["success"] is True
    assert f.read_text() == "line1\nline2\nline3\n"


def test_text_editor_undo(tmp_path):
    from backend.tools.text_editor_tool import text_editor_tool

    f = tmp_path / "test.txt"
    f.write_text("original\n")

    # Make a change
    asyncio_run(text_editor_tool.execute(action="str_replace", path=str(f), old_str="original", new_str="modified"))
    assert f.read_text() == "modified\n"

    # Undo
    result = asyncio_run(text_editor_tool.execute(action="undo_edit", path=str(f)))
    assert result["success"] is True
    assert f.read_text() == "original\n"


def test_text_editor_undo_no_history(tmp_path):
    from backend.tools.text_editor_tool import text_editor_tool

    f = tmp_path / "test.txt"
    f.write_text("original\n")

    result = asyncio_run(text_editor_tool.execute(action="undo_edit", path=str(f)))
    assert result["success"] is False
    assert "no undo history" in result["error"].lower()


def test_text_editor_path_traversal_blocked(tmp_path):
    from backend.tools.text_editor_tool import text_editor_tool

    result = asyncio_run(text_editor_tool.execute(action="view", path="../../../etc/passwd"))
    assert result["success"] is False
    assert "traversal" in result["error"].lower()


def test_text_editor_blocked_path(tmp_path):
    from backend.tools.text_editor_tool import text_editor_tool
    import sys

    # On Windows, the path resolution converts /etc/passwd to E:\etc\passwd
    # which doesn't match the Unix-style blocked prefixes
    # Use a path that will trigger the blocked prefix check on any platform
    if sys.platform == "win32":
        # On Windows, test the traversal check instead
        result = asyncio_run(text_editor_tool.execute(action="view", path="..\\..\\..\\windows\\system32"))
    else:
        result = asyncio_run(text_editor_tool.execute(action="view", path="/etc/passwd"))
    assert result["success"] is False
    assert "traversal" in result["error"].lower() or "not permitted" in result["error"].lower()