# Task 3.5 — Filesystem Tool Precision Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `FileSystemTool` so `read_file` supports line-based precise reads with numbered output and a new `replace_lines` method performs sed-style line-range edits, both registered and unit-tested.

**Architecture:** Extend `backend/tools/file_tool.py` (`FileSystemTool`): add `offset`/`limit` line-based numbered read mode to `read_file` (keeping the legacy whole-file char cap under a renamed `char_limit` param), and add a `replace_lines` method that replaces an inclusive 1-based line range and fails loudly on invalid input. Register `replace_lines` and document the new `read_file` mode in `backend/core/tool_registry.py`. Add a focused unit-test module. `text_editor_tool.py` is intentionally untouched.

**Tech Stack:** Python 3.11+, pytest, existing `FileSystemTool` / `_is_binary_file` helpers, `backend/core/tool_registry.py` `register_tool` API.

## Global Constraints

- Every public method returns a `Dict[str, Any]` and **never raises** on input/IO errors — errors are returned as `{"status": "error", "path": ..., "error": <str>}` dicts.
- Invalid/ambiguous input **fails loudly**: returns an error dict and performs **no** file write.
- `read_file` whole-file callers (`read_file(path)`) must stay backward compatible: same return keys (`status`, `path`, `content`, `size`, `truncated`).
- `replace_lines` is line-addressed (1-based, inclusive) — deterministic, no ambiguous-match failure mode.
- New tool entry authorized tiers: all tiers `0xxxx`–`9xxxx` (same as existing `read_file`).
- Numbered output format MUST match `text_editor_tool._view`: `"%6d\t" + line` per line, joined by `"\n"`.
- Tests must use `tmp_path` / `monkeypatch` — never real host paths.

---

### Task 1: Upgrade `read_file` with line-based precise, numbered output

**Files:**
- Modify: `backend/tools/file_tool.py:49-103` (`read_file` method)
- Test: `backend/tests/unit/test_file_system_tool.py` (create)

**Interfaces:**
- Consumes: existing `_is_binary_file(filepath)` (module-level, unchanged).
- Produces: `FileSystemTool.read_file(filepath, offset=1, limit=None, char_limit=1000)` returning either numbered precise output (`status`, `path`, `total_lines`, `content`, `truncated`) or legacy whole-file output (`status`, `path`, `content`, `size`, `truncated`) plus `total_lines`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_file_system_tool.py` with the following content (pytest injects `tmp_path`):

```python
# backend/tests/unit/test_file_system_tool.py
from backend.tools.file_tool import FileSystemTool


def _write(tmp_path, name, text):
    p = tmp_path / name
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/unit/test_file_system_tool.py -v`
Expected: FAIL — `read_file() got an unexpected keyword argument 'offset'` (and the numbered/error assertions fail).

- [ ] **Step 3: Implement the upgraded `read_file`**

Replace `backend/tools/file_tool.py:49-103` (the `read_file` method) with:

```python
    def read_file(
        self,
        filepath: str,
        offset: int = 1,
        limit: int | None = None,
        char_limit: int = 1000,
    ) -> Dict[str, Any]:
        """
        Read text file contents.

        Two modes:
        - Whole-file (default): offset=1 and limit=None. Returns raw text
          capped at char_limit*100 characters (legacy behavior).
        - Precise (line-based): offset/limit select an inclusive 1-based line
          range and the returned content is line-numbered ("%6d\\t" prefix),
          matching text_editor's view format.

        Returns an error dict (without raising) if:
        - The file is binary (PDF, image, archive, etc.)
        - The file cannot be decoded as UTF-8.
        - The path does not exist or is not accessible.
        - In precise mode, offset is out of range.

        Args:
            filepath:   Absolute or relative path to the file.
            offset:     1-based start line for precise mode (default 1).
            limit:      Number of lines to return in precise mode (None = whole file).
            char_limit: Legacy whole-file char cap = limit * 100 characters.
        """
        try:
            if _is_binary_file(filepath):
                return {
                    "status": "error",
                    "path": filepath,
                    "error": (
                        f"'{os.path.basename(filepath)}' is a binary file "
                        "(PDF, image, archive, etc.) and cannot be read as text. "
                        "Upload the file via the chat interface so the AI can "
                        "process its contents."
                    ),
                }

            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            total_lines = content.count("\n") + (0 if content.endswith("\n") or content == "" else 1)
            if content == "":
                total_lines = 0

            precise = (offset != 1) or (limit is not None)
            if not precise:
                char_cap = char_limit * 100
                truncated = len(content) > char_cap
                return {
                    "status":    "success",
                    "path":      filepath,
                    "content":   content[:char_cap],
                    "size":      len(content),
                    "total_lines": total_lines,
                    "truncated": truncated,
                }

            # Precise (line-based) mode
            lines = content.splitlines()
            total = len(lines)
            if offset < 1 or offset > total:
                return {
                    "status": "error",
                    "path":   filepath,
                    "error":  f"offset out of range (file has {total} lines)",
                }
            end = total if limit is None else min(offset + limit - 1, total)
            selected = lines[offset - 1 : end]
            numbered = "\n".join(
                f"{i + offset:>6}\t{line}" for i, line in enumerate(selected)
            )
            truncated = (limit is not None) and (offset + limit - 1 < total)
            return {
                "status":     "success",
                "path":       filepath,
                "total_lines": total,
                "content":    numbered,
                "truncated":  truncated,
            }
        except UnicodeDecodeError:
            return {
                "status": "error",
                "path":   filepath,
                "error":  (
                    f"'{os.path.basename(filepath)}' contains non-UTF-8 characters "
                    "and cannot be read as plain text."
                ),
            }
        except Exception as e:
            return {"status": "error", "path": filepath, "error": str(e)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/unit/test_file_system_tool.py -v`
Expected: PASS (all 4 tests).

- [ ] **Step 5: Commit**

```bash
git add -f backend/tools/file_tool.py backend/tests/unit/test_file_system_tool.py
git commit -m "feat(file_tool): add line-based precise, numbered read_file mode"
```

---

### Task 2: Add `replace_lines` (sed-style line-range edit)

**Files:**
- Modify: `backend/tools/file_tool.py` (add `replace_lines` method after `read_file`)
- Modify/Test: `backend/tests/unit/test_file_system_tool.py` (append tests)

**Interfaces:**
- Consumes: `_is_binary_file(filepath)` (module-level), `shutil` (already imported), `os` (already imported).
- Produces: `FileSystemTool.replace_lines(filepath, start_line, end_line, content, backup=True)` returning `{"status":"success","path","start_line","end_line","lines_replaced","bytes_written"}` or an error dict.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/unit/test_file_system_tool.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/unit/test_file_system_tool.py -v`
Expected: FAIL — `AttributeError: 'FileSystemTool' object has no attribute 'replace_lines'`.

- [ ] **Step 3: Implement `replace_lines`**

Add the following method to `FileSystemTool` (after `read_file`, before `write_file`):

```python
    def replace_lines(
        self,
        filepath: str,
        start_line: int,
        end_line: int,
        content: str,
        backup: bool = True,
    ) -> Dict[str, Any]:
        """
        Replace an inclusive 1-based line range [start_line, end_line] with
        `content` (may be multi-line). Lines outside the range are preserved.

        Fails loudly (error dict, no write) if:
        - start_line or end_line < 1
        - start_line > end_line
        - file is missing / not a file
        - start_line or end_line is out of range

        Args:
            filepath:   Target file path.
            start_line: 1-based start line (inclusive).
            end_line:   1-based end line (inclusive).
            content:    Replacement text (may be multi-line).
            backup:     If True, save a .bak copy before writing.
        """
        try:
            if _is_binary_file(filepath):
                return {
                    "status": "error",
                    "path": filepath,
                    "error": (
                        f"'{os.path.basename(filepath)}' is a binary file "
                        "(PDF, image, archive, etc.) and cannot be edited as text."
                    ),
                }

            if start_line < 1 or end_line < 1:
                return {
                    "status": "error",
                    "path":   filepath,
                    "error":  "start_line and end_line must be >= 1",
                }
            if start_line > end_line:
                return {
                    "status": "error",
                    "path":   filepath,
                    "error":  "start_line must be <= end_line",
                }
            if not os.path.isfile(filepath):
                return {
                    "status": "error",
                    "path":   filepath,
                    "error":  f"File not found: {filepath}",
                }

            with open(filepath, 'r', encoding='utf-8') as f:
                original = f.read()

            lines = original.splitlines(keepends=True)
            total = len(lines)

            if start_line > total:
                return {
                    "status": "error",
                    "path":   filepath,
                    "error":  f"start_line out of range (file has {total} lines)",
                }
            if end_line > total:
                return {
                    "status": "error",
                    "path":   filepath,
                    "error":  f"end_line out of range (file has {total} lines)",
                }

            if backup:
                shutil.copy2(filepath, f"{filepath}.bak")

            replacement = content if content.endswith("\n") else content + "\n"
            new_text = (
                "".join(lines[: start_line - 1])
                + replacement
                + "".join(lines[end_line:])
            )

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_text)

            return {
                "status":        "success",
                "path":          filepath,
                "start_line":    start_line,
                "end_line":      end_line,
                "lines_replaced": end_line - start_line + 1,
                "bytes_written": len(new_text.encode('utf-8')),
            }
        except Exception as e:
            return {"status": "error", "path": filepath, "error": str(e)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/unit/test_file_system_tool.py -v`
Expected: PASS (all tests, including the new 8).

- [ ] **Step 5: Commit**

```bash
git add -f backend/tools/file_tool.py backend/tests/unit/test_file_system_tool.py
git commit -m "feat(file_tool): add replace_lines line-range edit with loud failures"
```

---

### Task 3: Register `replace_lines` and document `read_file` in tool_registry

**Files:**
- Modify: `backend/core/tool_registry.py:489-510` (`read_file` registration block) and add `replace_lines` after `write_file`.

**Interfaces:**
- Consumes: `FileSystemTool` instance (already instantiated as `file_tool = FileSystemTool()` at line 490).
- Produces: Registered tools `read_file` (updated description) and `replace_lines` (new), callable by the agent runtime.

- [ ] **Step 1: Write a registration smoke test**

Append to `backend/tests/unit/test_file_system_tool.py`:

```python
def test_registry_exposes_replace_lines():
    from backend.core.tool_registry import ToolRegistry
    reg = ToolRegistry()
    reg.register_all_tools()  # safe: idempotent-ish for our assertion
    names = {t.name for t in reg._tools.values()} if hasattr(reg, "_tools") else set()
    # Fallback: assert the function resolves via get_tool
    fn = reg.get_tool("replace_lines")
    assert fn is not None
    assert callable(fn)
```

> Note: if `ToolRegistry` API differs, the implementer should locate the correct accessor (e.g. `get_tool(name)`) and assert `replace_lines` resolves to `file_tool.replace_lines`. Adjust the assertion to match the actual registry API rather than guessing.

- [ ] **Step 2: Run the smoke test to verify it fails**

Run: `cd backend && pytest tests/unit/test_file_system_tool.py::test_registry_exposes_replace_lines -v`
Expected: FAIL — `replace_lines` not registered (returns None / KeyError).

- [ ] **Step 3: Update `read_file` description and add `replace_lines` registration**

In `backend/core/tool_registry.py`, update the `read_file` entry's `description` to:

```python
            description=(
                "Read file contents from host filesystem. Whole-file mode returns "
                "raw text (legacy). Precise mode: pass offset (1-based start line) "
                "and/or limit (line count) to read a line range; in precise mode the "
                "returned content is line-numbered and includes total_lines."
            ),
```

And add, immediately after the `write_file` registration block (after line 510):

```python
        self.register_tool(
            name="replace_lines",
            description=(
                "Replace an inclusive 1-based line range [start_line, end_line] in a "
                "file with new content. Deterministic (line-addressed) — fails loudly "
                "if start_line/end_line are out of range or start_line > end_line. "
                "Optional .bak backup. Use read_file with offset/limit first to see "
                "line numbers."
            ),
            function=file_tool.replace_lines,
            parameters={
                "filepath":   {"type": "string",  "description": "Absolute file path"},
                "start_line": {"type": "integer", "description": "1-based start line (inclusive)"},
                "end_line":   {"type": "integer", "description": "1-based end line (inclusive)"},
                "content":    {"type": "string",  "description": "Replacement text (may be multi-line)"},
                "backup":     {"type": "boolean", "description": "Write a .bak copy first (default true)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx", "7xxxx", "8xxxx", "9xxxx"],
        )
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/unit/test_file_system_tool.py -v`
Expected: PASS (smoke test now resolves `replace_lines`).

- [ ] **Step 5: Commit**

```bash
git add -f backend/core/tool_registry.py backend/tests/unit/test_file_system_tool.py
git commit -m "feat(registry): register replace_lines, document read_file precise mode"
```

---

### Task 4: Final full test run + lint

**Files:**
- No new files. Verification only.

**Interfaces:**
- Consumes: all previously written code + tests.

- [ ] **Step 1: Run the full unit test module**

Run: `cd backend && pytest tests/unit/test_file_system_tool.py -v`
Expected: PASS (all 13 tests).

- [ ] **Step 2: Run project lint/typecheck if available**

Run: `cd backend && ruff check tools/file_tool.py core/tool_registry.py 2>/dev/null || python -m flake8 tools/file_tool.py core/tool_registry.py 2>/dev/null || echo "no linter configured — skipping"`
Expected: No new lint errors introduced.

- [ ] **Step 3: Commit any lint fixes (only if needed)**

```bash
git add -f backend/tools/file_tool.py backend/core/tool_registry.py
git commit -m "style(file_tool): lint fixes from precision upgrade"
```
(If no fixes were needed, skip this commit.)

---

## Self-Review Notes (per writing-plans skill)

- **Spec coverage:** §3.1 `read_file` precise+numbered → Task 1. §3.2 `replace_lines` → Task 2. §3.3 registry → Task 3. §3.4 tests → Tasks 1–3. All acceptance criteria mapped.
- **Placeholder scan:** No TBD/TODO. Registry smoke test includes a guarded note about exact API access; it instructs the implementer to match the real `ToolRegistry` API rather than guess — this is intentional guidance, not a missing implementation.
- **Type consistency:** `read_file(filepath, offset, limit, char_limit)` and `replace_lines(filepath, start_line, end_line, content, backup)` signatures are used identically across Tasks 1–3 and tests. Return dict keys (`status`, `path`, `total_lines`, `content`, `truncated`, `lines_replaced`, `bytes_written`, `start_line`, `end_line`, `error`) are consistent everywhere.
