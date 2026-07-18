# Full Tool Audit — Close Known Gaps (web_fetch, code_execution, tool_search)

> Date: 2026-07-18
> Status: approved design, pre-implementation
> Scope: add three missing agent tools to Agentium's `ToolRegistry`, each with a
> companion `SKILL.md` and unit + registration tests.

---

## 1. Context & Problem

§3.6 (P2) of the audit flags that Agentium agents (including Critics) lack
several tools a modern agent stack needs. A research pass against current 2026
agent-tooling standards (Claude Code, OpenAI Agents SDK, MCP production
patterns, AgentFetch) confirms three consistent, expected primitives:

1. **web_fetch** — retrieve a URL's *content* (HTML→Markdown), distinct from
   web search which only returns result lists.
2. **code_execution** — run code in a *sandboxed* environment, distinct from
   the shell/`execute_command` path and from Task-level remote execution.
3. **tool_search** — let an agent *discover* other tools + descriptions at
   runtime by capability/intent, instead of being handed the entire tool list.

Current state of the codebase (verified):

- `backend/tools/web_search_tool.py` exists (returns ranked result lists) but
  **no** tool retrieves a URL's body. `web_fetch` is the gap.
- `backend/services/remote_executor/service.py` (`RemoteExecutorService`) and
  `backend/api/routes/remote_executor.py` already implement a Docker-sandboxed
  code executor with an `execution_guard` and a summary-only contract. There is
  **no agent-facing tool** wrapping it — `code_execution` is the gap (it must
  *wrap*, not rebuild, the existing engine).
- `backend/core/tool_registry.py` holds ~100 registered tools and exposes
  `list_tools(tier)` (returns *all* authorized tools) but has **no search/
  discovery** entry point. `tool_search` is the gap.

Design follows `docs/documents/tool_and_skill_creation.md` (canonical worked
example: `vector_db` tool + skill added 2026-07-17).

---

## 2. Approach

**Selected: A — three independent tools, one per gap.** Each is a separate
`backend/tools/<name>_tool.py` module following the established
class/singleton/`execute(action=...)`/return-`{"success"/"status":...}` pattern
(template: `web_search_tool.py`). Each registers via `register_tool(...)` in
`tool_registry._initialize_tools`, ships a matching `SKILL.md`, and gets unit +
registration tests.

Rejected alternatives:
- **B — single "web intelligence" mega-tool** (fetch+search+extract bundled):
  contradicts the repo's one-action-per-tool convention and bloats the schema.
- **C — extend `web_search` + add a generic `discover` only**: leaves the
  `code_execution` gap unclosed; also, full progressive/deferred tool loading is
  a larger architectural change outside this task's scope.

---

## 3. Tools

### 3.1 `web_fetch`

**File:** `backend/tools/web_fetch_tool.py`
**Pattern:** class `WebFetchTool` + module singleton `web_fetch_tool`, lazy httpx
client, `async def execute(action, **kwargs)`.

**Actions**
- `fetch` — primary. Params:
  - `url` (string, required): target URL.
  - `max_tokens` (integer, optional, default 4000): truncate returned Markdown
    to roughly this token budget to protect context.
  - `use_cache` (boolean, optional, default true): serve cached result if
    <5 min old.
  - `allowed_domains` (array, optional): if set, only these domains (suffix
    match) are permitted; others return a clean error.
- `help` — points to the skill file path.

**Behavior**
- Fetch via `httpx.AsyncClient` with a browser UA and a timeout (~12s).
- Extract content to Markdown: prefer `trafilatura` (local, zero-cost) for HTML;
  if unavailable fall back to `markdownify`/`html2text`, else strip tags to raw
  text. PDFs: if `pypdf`/`PyPDF2` present, extract text; otherwise return a
  clear "PDF extraction unavailable" note rather than failing loudly.
- Token estimation (cheap `len(text)//4`) used to truncate at `max_tokens`.
- Redis cache (TTL 300s) keyed by `sha256(url:max_tokens)`; cache misses are
  silent and fall through to a live fetch.
- Never raise into the agent context. All failures return
  `{"status":"error","error": "..."}`.

**Return shape (success)**
```
{
  "status": "success",
  "url": str,
  "title": str,
  "markdown": str,        # truncated to max_tokens
  "token_count": int,
  "cached": bool,
  "truncated": bool
}
```

**Tiers:** all — `["0xxxx"…"9xxxx"]` (read-mostly, like `web_search`).

### 3.2 `code_execution`

**File:** `backend/tools/code_execution_tool.py`
**Pattern:** class `CodeExecutionTool` + singleton `code_execution_tool`; wraps
`RemoteExecutorService`.

**Actions**
- `execute` — Params:
  - `code` (string, required): source to run (default language python).
  - `language` (string, optional, default "python").
  - `dependencies` (array, optional): pip packages to install in sandbox.
  - `input_data` (any, optional): exposed to code as `input_data`.
  - `timeout_seconds` (integer, optional, default 300).
  - `network_access` (boolean, optional, default false).
  - `agent_id` (string, optional): auto-injected by executor for tier auth; the
    tool passes the caller's id through so the service's guard applies.
- `help` — documents the summary-only contract and that raw data never leaves
  the sandbox.

**Behavior**
- Constructs `RemoteExecutorService(db=None)` (service is DB-optional) and calls
  `await service.execute(...)` with the caller `agent_id`.
- Reuses the existing `execution_guard` validation and Docker sandbox — no new
  execution infrastructure.
- Returns the service's summary dict unchanged (`status`, summary, stats,
  error_message, execution_time_ms, etc.). Raw data is never returned.

**Return shape:** the `RemoteExecutorService.execute` summary dict.

**Tiers:** restricted — `["0xxxx","1xxxx","2xxxx"]` (privileged, consistent
with `execute_command` per §2.4). Task tiers (3xxxx–6xxxx) and Critics
(7xxxx–9xxxx) are withheld.

### 3.3 `tool_search`

**File:** `backend/tools/tool_search_tool.py`
**Pattern:** class `ToolSearchTool` + singleton `tool_search_tool`.

**Actions**
- `search` — Params:
  - `query` (string, required): natural-language need / capability phrase.
  - `limit` (integer, optional, default 10): max results.
  - `tier` (string, optional): which tier's authorized tool set to search;
    defaults to the caller's tier passed via `agent_id`/context. Must never
    surface tools the caller's tier cannot use.
- `get` — Params:
  - `name` (string, required): return the full descriptor (description +
    parameters) for one tool, if authorized for the caller's tier.
- `help` — points to the skill file path.

**Behavior**
- Calls `tool_registry.list_tools(caller_tier)` to get only authorized tools.
- Scores each tool by combined match over `name` + `description` +
  parameter names/descriptions: token overlap (case-insensitive) plus a small
  boost for name/substring hits. No new vector store required — the registry is
  small enough for in-memory scoring; this keeps the tool dependency-free and
  fast. (If semantic ranking is later desired, this is the swap point.)
- Returns ranked `[{name, description, score, match_reason}]`.
- `get` returns the descriptor or `{"status":"error","error":"not found /
  not authorized"}`.

**Return shape (search success)**
```
{
  "status": "success",
  "query": str,
  "count": int,
  "results": [
    {"name": str, "description": str, "score": float, "match_reason": str},
    ...
  ]
}
```

**Tiers:** all — `["0xxxx"…"9xxxx"]`.

---

## 4. Registration

In `backend/core/tool_registry.py::_initialize_tools`, add (near siblings):
- `web_fetch` block near the `web_search` block (~line 228).
- `code_execution` block near the remote-execution / `remote_exec_tool` block.
- `tool_search` block near the governance/tool_creator tools.

Each `register_tool` supplies `name`, `description` (with a pointer to its
`SKILL.md`), `function=<singleton>.execute`, `parameters` (marking optional via
`"optional": True`), and `authorized_tiers` per §3.1/§3.2/§3.3.

Imports added at the top of `tool_registry.py`:
```python
from backend.tools.web_fetch_tool     import web_fetch_tool
from backend.tools.code_execution_tool import code_execution_tool
from backend.tools.tool_search_tool    import tool_search_tool
```

---

## 5. Skills

Each tool gets `backend/.agentium/skills/<name>/SKILL.md` (frontmatter per
`tool_and_skill_creation.md` §3.1: `name`, `description` 50–300 chars written
as the query an agent would type, `skill_type`, `domain`, `complexity`, `tags`,
`creator_tier`). Indexed into ChromaDB via `backend/scripts/seed_skills.py`.

| Skill | skill_type | domain | complexity | tags |
|---|---|---|---|---|
| web_fetch | research | general | beginner | web, fetch, scraping, markdown |
| code_execution | automation | backend | intermediate | code, sandbox, execution, docker |
| tool_search | integration | ai | beginner | discovery, tools, registry |

---

## 6. Testing

Per `tool_and_skill_creation.md` §2.5:

- **Unit** (`backend/tests/unit/test_<name>_tool.py`): mock the heavy
  dependency via `monkeypatch.setattr` on the module-level import
  (`web_fetch_tool`'s httpx client; `code_execution_tool`'s
  `RemoteExecutorService.execute`; `tool_search_tool`'s `tool_registry`). Use
  `Fake*` classes. Cover: success path, timeout/error path, truncation
  (web_fetch), tier-withheld (code_execution via `execute`'s guard), empty
  query (tool_search).
- **Registration** (`backend/tests/integration/test_<name>_registration.py`):
  assert the tool is in `tool_registry.tools`, appears in
  `list_tools(tier)` for each intended tier, is exported by `to_openai_tools` /
  `to_anthropic_tools` with correct `required` params, and (for code_execution)
  is *absent* for Task/Critic tiers.

Run in container, coverage gate off:
```bash
docker compose exec -T backend bash -lc \
  "cd /app/backend && pytest tests/unit/test_web_fetch_tool.py tests/unit/test_code_execution_tool.py tests/unit/test_tool_search_tool.py -o addopts='' -q"
```

---

## 7. Error Handling & Safety

- **web_fetch:** network timeouts, non-200, and oversized pages are truncated
  or returned as clean `{"status":"error"}` — never raise into agent context.
  `allowed_domains` violations return a clean error. Cache failures are silent.
- **code_execution:** delegates to `execution_guard` + Docker sandbox; invalid
  or disallowed code returns `{"status":"error"}` without executing. Tier gate
  enforced both at registration (`authorized_tiers`) and inside the executor
  via the caller `agent_id` (defense in depth, per §2.4).
- **tool_search:** empty/missing query returns a helpful message; results are
  always scoped to the caller's authorized tier — never leaks tools a tier
  cannot use.

---

## 8. Acceptance Criteria

1. All three tools (`web_fetch`, `code_execution`, `tool_search`) exist as
   registered `ToolRegistry` entries with correct `authorized_tiers`.
2. `web_fetch` retrieves a URL and returns truncated Markdown + metadata; does
   not raise on failure.
3. `code_execution` wraps `RemoteExecutorService`, returns only summaries, and
   is callable only by 0xxxx/1xxxx/2xxxx.
4. `tool_search` returns ranked tools scoped to the caller tier; `get` returns a
   single tool descriptor.
5. Each tool has a matching `SKILL.md`, indexed into ChromaDB.
6. Each tool has unit + registration tests that pass.

---

## 9. Out of Scope (YAGNI)

- Full progressive/deferred tool-loading (hiding schemas until runtime). The
  registry is small; `tool_search` covers the discovery need without that
  architectural change.
- New sandbox infrastructure; agent-facing MCP-server discovery beyond built-in
  tools; PDF/JS-heavy page rendering via headless browser (noted as limitation).
