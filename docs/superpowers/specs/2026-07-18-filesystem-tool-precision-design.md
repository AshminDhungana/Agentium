# Task 3.5 — Upgrade `FileSystemTool` Read/Write to Modern Coding-Agent Standards

**File:** `docs/superpowers/specs/2026-07-18-filesystem-tool-precision-design.md`
**Date:** 2026-07-18
**Source task:** `docs/documents/todo_verify.md` §3.5 — *[P2] Upgrade read/write tools to modern coding-agent standards*

## 1. Problem

The agent-facing file read/write tool (`backend/tools/file_tool.py`, class `FileSystemTool`) is coarse compared to the precision modern coding agents expect:

- `read_file(filepath, limit=1000)` reads the **entire** file and returns raw, un-numbered text. There is no way to read a precise line range (`offset`/`limit`), and the returned content is not line-numbered, so an agent cannot reliably cite or target line numbers.
- `write_file` only supports full-file overwrite. There is no targeted, sed-style edit (replace by exact string or by line range) exposed from `FileSystemTool`.

The companion `backend/tools/text_editor_tool.py` (`TextEditorTool`) already meets the modern bar (`view` with numbered lines + range, `str_replace` that fails loudly on non-unique matches, `insert`, `undo_edit`). Task 3.5 therefore targets `FileSystemTool` only; `TextEditorTool` is left unchanged.

## 2. Goal & Scope

Upgrade `FileSystemTool` so that:

1. `read_file` supports **line-based precise reads** (`offset`/`limit`) and returns **line-numbered** output mirrored from `TextEditorTool._view`.
2. `FileSystemTool` gains a **sed-style precise edit** — `replace_lines`, which replaces an inclusive 1-based line range, addressed by line number (deterministic, no ambiguous-match risk).
3. Both new capabilities are **registered as tool entries** in `backend/core/tool_registry.py` and covered by **unit tests**.
4. Invalid/ambiguous input **fails loudly** (returns an error dict, makes no silent partial change).

**In scope:**
- `FileSystemTool.read_file` — add `offset`/`limit` line-based mode + numbered output; keep `char_limit` backward-compat.
- `FileSystemTool.replace_lines` — new method.
- New registry entries `replace_lines`; updated `read_file` description/params.
- New unit tests.

**Out of scope:** `TextEditorTool` (already modern), `write_file` full-overwrite (unchanged), `DesktopTool`, other tools.

## 3. Design

### 3.1 `read_file` — upgraded (precise, line-based, numbered)

**Signature:**
```python
def read_file(
    self,
    filepath: str,
    offset: int = 1,        # 1-based start line for precise mode
    limit: int | None = None,  # number of lines to return (None = whole file)
    char_limit: int = 1000,    # legacy whole-file char cap (limit * 100 chars)
) -> Dict[str, Any]
```

**Behavior:**
- Binary guard: if `_is_binary_file(filepath)` → return existing binary error dict (unchanged).
- UTF-8 decode error and OS-error → existing error dicts (unchanged).
- **Precise mode** is active when `offset != 1` or `limit is not None`:
  - Split file into lines via `splitlines()`.
  - Validate: `offset >= 1`; if `limit is not None` then `offset + limit - 1 <= total_lines` is **not** required to error (a short tail is returned gracefully), but `offset > total_lines` → error `"offset out of range (file has N lines)"`.
  - Selected lines are joined with the **same numbering format as `TextEditorTool._view`**: `"%6d\t" + line`, with the real 1-based line number as the prefix.
  - `truncated` reflects whether the selected slice is shorter than the file.
- **Whole-file mode** (default, `offset=1` and `limit=None`): preserves existing behavior — reads entire content, `char_limit` caps returned characters (`char_limit * 100`), returns raw `content` **without** line numbers (backward compatible). `total_lines` is still included for convenience.

**Return shape (precise mode):**
```python
{
    "status": "success",
    "path": filepath,
    "total_lines": N,
    "content": "<numbered lines, \n-joined>",
    "truncated": bool,
}
```
**Return shape (whole-file mode):** unchanged existing shape (`status`, `path`, `content`, `size`, `truncated`) plus optional `total_lines`.

### 3.2 `replace_lines` — sed-style precise edit (by line number)

**Signature:**
```python
def replace_lines(
    self,
    filepath: str,
    start_line: int,        # 1-based, inclusive
    end_line: int,          # 1-based, inclusive
    content: str,           # replacement text (may be multi-line)
    backup: bool = True,
) -> Dict[str, Any]
```

**Behavior:**
- Binary guard: if `_is_binary_file(filepath)` → binary error (unchanged pattern).
- Validate inputs **loudly** (return error dict, no write performed):
  - `start_line < 1` or `end_line < 1` → `"start_line/end_line must be >= 1"`.
  - `start_line > end_line` → `"start_line must be <= end_line"`.
  - File missing or not a file → existing-style not-found error.
- Read all lines via `splitlines(keepends=True)`; `total = len(lines)`.
- `start_line > total` → `"start_line out of range (file has N lines)"`.
  - `end_line > total` → `"end_line out of range (file has N lines)"`. (Both bounds checked before any write.)
- Build new content: `lines[0:start_line-1]` + normalized `content` + `lines[end_line:]`.
  - Normalize `content` so the replacement is line-joined correctly regardless of whether it ends in a newline; preserve the trailing newline structure of the original file (i.e. if the file ended with `\n`, the result keeps a trailing `\n`).
- Optional `.bak` backup (mirrors `write_file`): if `backup and os.path.exists(filepath)`, `shutil.copy2(filepath, f"{filepath}.bak")` before writing.
- Write new text as UTF-8.

**Return shape (success):**
```python
{
    "status": "success",
    "path": filepath,
    "start_line": start_line,
    "end_line": end_line,
    "lines_replaced": (end_line - start_line + 1),
    "bytes_written": <utf-8 byte length>,
}
```

**Determinism note:** Because replacement is addressed by absolute line numbers, there is no ambiguous-match failure mode (unlike string-based `str_replace`). This is the intended distinction from `TextEditorTool.str_replace`.

### 3.3 Registry changes (`backend/core/tool_registry.py`)

- **Existing** `read_file` / `write_file` entries: left exactly as-is (backward compatible). Update `read_file`'s `description` to mention the `offset`/`limit` line-based numbered mode and that whole-file mode is preserved.
- **New** `replace_lines` entry:
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
          "filepath":    {"type": "string",  "description": "Absolute file path"},
          "start_line":  {"type": "integer", "description": "1-based start line (inclusive)"},
          "end_line":    {"type": "integer", "description": "1-based end line (inclusive)"},
          "content":     {"type": "string",  "description": "Replacement text (may be multi-line)"},
          "backup":      {"type": "boolean", "description": "Write a .bak copy first (default true)", "optional": True},
      },
      authorized_tiers=["0xxxx","1xxxx","2xxxx","3xxxx","4xxxx","5xxxx","6xxxx","7xxxx","8xxxx","9xxxx"],
  )
  ```

### 3.4 Tests (`backend/tests/unit/test_file_system_tool.py`, new)

Using `tmp_path` fixtures (no real host paths):

1. **Whole-file regression** — `read_file(path)` returns full content, `total_lines` correct, `truncated=False`, no line-number prefix.
2. **Precise slice** — `read_file(path, offset=2, limit=3)` returns lines 2–4 with `%6d\t` numbering; correct `total_lines`.
3. **Offset out of range** — `read_file(path, offset=total+1)` returns error.
4. **Binary guard** — `read_file` on a PDF/zip fixture returns the binary error (unchanged behavior).
5. **replace_lines single line** — replaces line 3; surrounding lines preserved; `lines_replaced=1`.
6. **replace_lines range** — replaces lines 2–4 with multi-line content; tail preserved.
7. **replace_lines append/truncate** — `end_line == total` replaces last line; documented behavior.
8. **Loud failures** — `start_line > end_line`, `start_line > total`, `end_line > total`, missing file → each returns an error dict and **does not modify** the file (assert file bytes unchanged).
9. **Backup** — `replace_lines(..., backup=True)` creates `<path>.bak` with original content; `backup=False` does not.

All tests assert the dict `status` field and required keys; no test relies on logs.

## 4. Acceptance Criteria (from task 3.5)

- New `read_file` supports `offset`/`limit` and returns line-numbered output; whole-file callers unaffected.
- New `replace_lines` supports exact line-range replace and **fails loudly** (error dict, no silent partial change) on out-of-range / invalid input.
- Both capabilities registered in `tool_registry.py` with correct (all-tier) authorization.
- Both covered by unit tests (`backend/tests/unit/test_file_system_tool.py`).

## 5. Files Touched

| File | Change |
|------|--------|
| `backend/tools/file_tool.py` | Add `offset`/`limit` line-based numbered mode to `read_file`; add `replace_lines` method. |
| `backend/core/tool_registry.py` | Document `read_file` new mode; add `replace_lines` entry. |
| `backend/tests/unit/test_file_system_tool.py` | New unit test module (9 cases). |

## 6. Non-Goals / Risks

- Not touching `TextEditorTool` — it already meets the bar; duplicating `str_replace` here was explicitly excluded by scope decision.
- `read_file` retains a dual notion of `limit` (legacy char cap vs new line count). Resolved by: legacy `char_limit` param name is explicit; line-based `limit` only applies in precise mode. Documented in registry description.
- No `insert_lines` / `str_replace` added to `FileSystemTool` (deferred — `TextEditorTool` covers them).
