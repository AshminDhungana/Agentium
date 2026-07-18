# Tool Audit Gaps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three missing agent tools — `web_fetch`, `code_execution`, `tool_search` — to Agentium's `ToolRegistry`, each with a companion `SKILL.md` and unit + registration tests.

**Architecture:** Three independent `backend/tools/<name>_tool.py` modules following the existing class/singleton/`execute(action=...)`/return-`{"status":...}` pattern (template: `web_search_tool.py`). `code_execution` wraps the existing `RemoteExecutorService` (Docker sandbox) rather than building new execution infra. Each tool registers via `register_tool(...)` in `tool_registry._initialize_tools`, ships a `SKILL.md` under `backend/.agentium/skills/<name>/`, and is indexed into ChromaDB by `seed_skills.py`.

**Tech Stack:** Python 3.13, FastAPI/asyncio, httpx (already a dep), `trafilatura`/`markdownify`/`pypdf` (optional, import-guarded), Redis cache (fail-silent), `RemoteExecutorService` + `execution_guard`, pytest (`asyncio_mode = auto`).

## Global Constraints

- Every tool module: class + module-level singleton, `async def execute(self, action: str, **kwargs) -> Dict[str, Any]`, lazy-init heavy deps, returns `{"status": "success"/"error", ...}`.
- `register_tool(name, description, function, parameters, authorized_tiers)` — params mark `"optional": True` to exclude from `required`.
- Tier gates are enforced **only** via `authorized_tiers` in `register_tool` (the export methods `to_openai_tools`/`to_anthropic_tools` filter solely on `authorized_tiers`; the Task-tier `restricted_tools_for` list only blocks `spawn_agent`/`dispatch_task`/`create_task`, so new tool names are unaffected).
- `web_fetch` tiers: all `["0xxxx"…"9xxxx"]`. `code_execution` tiers: `["0xxxx","1xxxx","2xxxx"]`. `tool_search` tiers: all `["0xxxx"…"9xxxx"]`.
- SKILL.md frontmatter must include `name`, `description` (50–300 chars, written as the query an agent would type), `skill_type`, `domain`, `complexity`, `tags`, `creator_tier`. Body splits on `##` into steps/validation.
- Tests: unit under `backend/tests/unit/`, registration under `backend/tests/integration/` (importing `tool_registry` pulls the whole graph). Run in container with coverage gate off: `docker compose exec -T backend bash -lc "cd /app/backend && pytest <path> -o addopts='' -q"`.
- YAGNI: no deferred tool-loading; no new sandbox infra; no browser rendering for JS-heavy pages (noted as limitation).
- Note: `docs/superpowers/` is gitignored; specs/plans live in `docs/specs/` and `docs/plans/`.

---

### Task 1: `web_fetch` tool

**Files:**
- Create: `backend/tools/web_fetch_tool.py`
- Test: `backend/tests/unit/test_web_fetch_tool.py`
- Test: `backend/tests/integration/test_web_fetch_registration.py`

**Interfaces:**
- Consumes: `httpx.AsyncClient` (lazy), optional `trafilatura`/`markdownify`/`pypdf`, `backend.core.cache` or raw redis via `backend.core.redis` (fail-silent).
- Produces: `web_fetch_tool.execute(action, **kwargs)` → dict; singleton `web_fetch_tool`.

- [ ] **Step 1: Write the failing unit test**

```python
# backend/tests/unit/test_web_fetch_tool.py
import asyncio
from types import SimpleNamespace
from backend.tools import web_fetch_tool


def test_fetch_success_truncates(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200
        text = "<html><head><title>Hi</title></head><body>" + ("x" * 100000) + "</body></html>"
        headers = {"content-type": "text/html"}

    class FakeClient:
        async def get(self, url, **kw):
            captured["url"] = url
            return FakeResp()

    monkeypatch.setattr(web_fetch_tool, "_client", FakeClient())
    # force no extraction lib so it falls back to raw strip
    monkeypatch.setattr(web_fetch_tool, "_extract", lambda html, url: html)

    result = asyncio.get_event_loop().run_until_complete(
        web_fetch_tool.execute("fetch", url="https://example.com", max_tokens=100)
    )
    assert result["status"] == "success"
    assert result["title"] == "Hi"
    assert result["truncated"] is True
    assert result["token_count"] <= 200


def test_fetch_blocks_disallowed_domain(monkeypatch):
    monkeypatch.setattr(web_fetch_tool, "_client", None)
    result = asyncio.get_event_loop().run_until_complete(
        web_fetch_tool.execute(
            "fetch", url="https://evil.com", allowed_domains=["good.com"]
        )
    )
    assert result["status"] == "error"
    assert "domain" in result["error"].lower()


def test_help_action():
    result = asyncio.get_event_loop().run_until_complete(web_fetch_tool.execute("help"))
    assert result["status"] == "success"
    assert "SKILL.md" in result["description"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/unit/test_web_fetch_tool.py -o addopts='' -q"`
Expected: ERROR/FAIL — `ModuleNotFoundError: backend.tools.web_fetch_tool`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/tools/web_fetch_tool.py
"""Web Fetch Tool — retrieve a URL's content as clean Markdown.

Distinct from web_search (which returns result lists). Returns truncated
Markdown + metadata + token count. Lazy httpx client; optional extraction
libs (trafilatura / markdownify / pypdf) import-guarded; Redis cache is
fail-silent. All failures return {"status":"error"} — never raise into the
agent context. Registered in ToolRegistry as "web_fetch".
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300
_DEFAULT_MAX_TOKENS = 4000
_REQUEST_TIMEOUT = 12.0
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _extract_markdown(html: str, url: str) -> str:
    try:
        import trafilatura  # type: ignore
        extracted = trafilatura.extract(html, url=url)
        if extracted:
            return extracted
    except Exception:
        pass
    try:
        import markdownify  # type: ignore
        return markdownify.markdownify(html)
    except Exception:
        pass
    # last-resort: strip tags
    return re.sub(r"<[^>]+>", "", html)


def _extract_pdf(payload: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(__import__("io").BytesIO(payload))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        return ""


class WebFetchTool:
    TOOL_NAME = "web_fetch"
    AUTHORIZED_TIERS = [f"{i}xxxx" for i in range(10)]

    def __init__(self) -> None:
        self._client = None
        self._redis = None

    @property
    def client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT, headers={"User-Agent": _USER_AGENT}
            )
        return self._client

    def _cache_key(self, url: str, max_tokens: int) -> str:
        digest = hashlib.sha256(f"{url.strip().lower()}:{max_tokens}".encode()).hexdigest()[:16]
        return f"agentium:web_fetch:{digest}"

    def _get_cache(self, key: str) -> Optional[str]:
        try:
            import redis  # type: ignore
            if self._redis is None:
                from backend.core.config import settings
                self._redis = redis.from_url(settings.REDIS_URL)
            val = self._redis.get(key)
            return val.decode() if val else None
        except Exception:
            return None

    def _set_cache(self, key: str, value: str) -> None:
        try:
            if self._redis is None:
                from backend.core.config import settings
                import redis  # type: ignore
                self._redis = redis.from_url(settings.REDIS_URL)
            self._redis.set(key, value, ex=_CACHE_TTL_SECONDS)
        except Exception:
            pass

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        if action == "help":
            return {
                "status": "success",
                "description": (
                    "Fetch a URL and return its content as clean Markdown with a token "
                    "budget. Full reference in backend/.agentium/skills/web_fetch/SKILL.md."
                ),
            }
        if action != "fetch":
            return {"status": "error", "error": f"Unknown action: {action}"}

        url = (kwargs.get("url") or "").strip()
        if not url:
            return {"status": "error", "error": "url is required"}
        max_tokens = int(kwargs.get("max_tokens", _DEFAULT_MAX_TOKENS))
        allowed = kwargs.get("allowed_domains") or []
        use_cache = bool(kwargs.get("use_cache", True))

        if allowed:
            host = re.sub(r"^https?://", "", url).split("/")[0].lower()
            if not any(host == d.lower() or host.endswith("." + d.lower()) for d in allowed):
                return {"status": "error", "error": f"domain not allowed: {host}"}

        cache_key = self._cache_key(url, max_tokens)
        if use_cache:
            cached = self._get_cache(cache_key)
            if cached is not None:
                return {
                    "status": "success", "url": url, "title": "",
                    "markdown": cached, "token_count": _estimate_tokens(cached),
                    "cached": True, "truncated": False,
                }

        try:
            resp = await self.client.get(url, follow_redirects=True)
        except Exception as exc:
            return {"status": "error", "error": f"fetch failed: {exc}"}
        if resp.status_code >= 400:
            return {"status": "error", "error": f"HTTP {resp.status_code}"}

        ctype = resp.headers.get("content-type", "").lower()
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            markdown = _extract_pdf(resp.content)
            if not markdown:
                return {"status": "error", "error": "PDF extraction unavailable"}
        else:
            markdown = _extract_markdown(resp.text, url)

        title = ""
        m = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
        if m:
            title = m.group(1).strip()

        token_count = _estimate_tokens(markdown)
        truncated = False
        if token_count > max_tokens:
            markdown = markdown[: max_tokens * 4]
            token_count = _estimate_tokens(markdown)
            truncated = True

        if use_cache:
            self._set_cache(cache_key, markdown)
        return {
            "status": "success", "url": url, "title": title,
            "markdown": markdown, "token_count": token_count,
            "cached": False, "truncated": truncated,
        }


web_fetch_tool = WebFetchTool()
```

- [ ] **Step 4: Run unit test to verify it passes**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/unit/test_web_fetch_tool.py -o addopts='' -q"`
Expected: PASS (3 passed)

- [ ] **Step 5: Write the registration test**

```python
# backend/tests/integration/test_web_fetch_registration.py
from backend.core.tool_registry import tool_registry


def test_web_fetch_registered():
    assert "web_fetch" in tool_registry.tools
    tool = tool_registry.get_tool("web_fetch")
    assert set(tool["authorized_tiers"]) == {f"{i}xxxx" for i in range(10)}


def test_web_fetch_in_openai_and_anthropic_all_tiers():
    for tier in [f"{i}xxxx" for i in range(10)]:
        names = [t["function"]["name"] for t in tool_registry.to_openai_tools(tier)]
        assert "web_fetch" in names
        names_a = [t["name"] for t in tool_registry.to_anthropic_tools(tier)]
        assert "web_fetch" in names_a


def test_web_fetch_required_param():
    props, required = tool_registry._build_props(tool_registry.get_tool("web_fetch"))
    assert "url" in required
    assert "max_tokens" not in required
```

- [ ] **Step 6: Run registration test**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/integration/test_web_fetch_registration.py -o addopts='' -q"`
Expected: FAIL — `web_fetch` not yet in registry (Task 4 wires it).

- [ ] **Step 7: Commit**

```bash
git add backend/tools/web_fetch_tool.py backend/tests/unit/test_web_fetch_tool.py backend/tests/integration/test_web_fetch_registration.py
git commit -m "feat: add web_fetch tool (HTML->Markdown, token-budgeted, cached)"
```

---

### Task 2: `code_execution` tool

**Files:**
- Create: `backend/tools/code_execution_tool.py`
- Test: `backend/tests/unit/test_code_execution_tool.py`
- Test: `backend/tests/integration/test_code_execution_registration.py`

**Interfaces:**
- Consumes: `backend.services.remote_executor.service.RemoteExecutorService` (constructor `RemoteExecutorService(db_session=None)`; `.execute(code, agent_id, task_id=None, language="python", dependencies=None, input_data=None, timeout_seconds=300, memory_limit_mb=512, cpu_limit=1.0, network_access=False) -> dict`). The service enforces `execution_guard` and the summary-only contract.
- Produces: `code_execution_tool.execute(action, **kwargs)` → dict (passes through service summary); singleton `code_execution_tool`. `agent_id` is injected by the executor framework; the tool forwards it to the service so the guard's tier check applies.

- [ ] **Step 1: Write the failing unit test**

```python
# backend/tests/unit/test_code_execution_tool.py
import asyncio
from types import SimpleNamespace
from backend.tools import code_execution_tool


def test_execute_calls_service(monkeypatch):
    calls = {}

    class FakeService:
        async def execute(self, **kw):
            calls.update(kw)
            return {"status": "success", "summary": "ok", "execution_time_ms": 1}

    monkeypatch.setattr(code_execution_tool, "_make_service", lambda: FakeService())
    result = asyncio.get_event_loop().run_until_complete(
        code_execution_tool.execute(
            "execute", code="print(1)", agent_id="00001", language="python"
        )
    )
    assert result["status"] == "success"
    assert calls["code"] == "print(1)"
    assert calls["agent_id"] == "00001"
    assert calls["language"] == "python"


def test_blocked_code_returns_error(monkeypatch):
    class FakeService:
        async def execute(self, **kw):
            return {"status": "blocked", "error": "forbidden syscall", "security_result": {"passed": False}}

    monkeypatch.setattr(code_execution_tool, "_make_service", lambda: FakeService())
    result = asyncio.get_event_loop().run_until_complete(
        code_execution_tool.execute("execute", code="import os; os.system('x')", agent_id="00001")
    )
    assert result["status"] == "blocked"


def test_help_action():
    result = asyncio.get_event_loop().run_until_complete(code_execution_tool.execute("help"))
    assert result["status"] == "success"
    assert "sandbox" in result["description"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/unit/test_code_execution_tool.py -o addopts='' -q"`
Expected: ERROR/FAIL — `ModuleNotFoundError: backend.tools.code_execution_tool`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/tools/code_execution_tool.py
"""Code Execution Tool — run code in the existing Docker sandbox.

Thin wrapper over RemoteExecutorService (brains vs hands). Reuses the
execution_guard security check and the summary-only contract — raw data never
leaves the sandbox. Distinct from execute_command (shell, 0/1/2xxxx) and from
Task-level remote execution. Registered in ToolRegistry as "code_execution",
restricted to 0xxxx/1xxxx/2xxxx.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CodeExecutionTool:
    TOOL_NAME = "code_execution"
    AUTHORIZED_TIERS = ["0xxxx", "1xxxx", "2xxxx"]

    def _make_service(self):
        from backend.services.remote_executor.service import RemoteExecutorService
        return RemoteExecutorService(db_session=None)

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        if action == "help":
            return {
                "status": "success",
                "description": (
                    "Execute code in an isolated Docker sandbox. Raw data never leaves "
                    "the sandbox; you receive only a structured summary. Full reference "
                    "in backend/.agentium/skills/code_execution/SKILL.md."
                ),
            }
        if action != "execute":
            return {"status": "error", "error": f"Unknown action: {action}"}

        code = kwargs.get("code")
        if not code:
            return {"status": "error", "error": "code is required"}
        agent_id = kwargs.get("agent_id") or "00001"

        service = self._make_service()
        try:
            result = await service.execute(
                code=code,
                agent_id=agent_id,
                task_id=kwargs.get("task_id"),
                language=kwargs.get("language", "python"),
                dependencies=kwargs.get("dependencies"),
                input_data=kwargs.get("input_data"),
                timeout_seconds=int(kwargs.get("timeout_seconds", 300)),
                network_access=bool(kwargs.get("network_access", False)),
            )
        except Exception as exc:
            logger.exception("code_execution failed")
            return {"status": "error", "error": str(exc)}
        return result


code_execution_tool = CodeExecutionTool()
```

- [ ] **Step 4: Run unit test to verify it passes**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/unit/test_code_execution_tool.py -o addopts='' -q"`
Expected: PASS (3 passed)

- [ ] **Step 5: Write the registration test**

```python
# backend/tests/integration/test_code_execution_registration.py
from backend.core.tool_registry import tool_registry

ALLOWED = ["0xxxx", "1xxxx", "2xxxx"]
WITHHELD = [f"{i}xxxx" for i in (3, 4, 5, 6, 7, 8, 9)]


def test_code_execution_registered():
    assert "code_execution" in tool_registry.tools
    tool = tool_registry.get_tool("code_execution")
    assert tool["authorized_tiers"] == ALLOWED


def test_code_execution_visible_only_to_allowed_tiers():
    for tier in ALLOWED:
        names = [t["function"]["name"] for t in tool_registry.to_openai_tools(tier)]
        assert "code_execution" in names
    for tier in WITHHELD:
        names = [t["function"]["name"] for t in tool_registry.to_openai_tools(tier)]
        assert "code_execution" not in names


def test_code_execution_required_param():
    props, required = tool_registry._build_props(tool_registry.get_tool("code_execution"))
    assert "code" in required
    assert "language" not in required
```

- [ ] **Step 6: Run registration test**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/integration/test_code_execution_registration.py -o addopts='' -q"`
Expected: FAIL — `code_execution` not yet in registry (Task 4 wires it).

- [ ] **Step 7: Commit**

```bash
git add backend/tools/code_execution_tool.py backend/tests/unit/test_code_execution_tool.py backend/tests/integration/test_code_execution_registration.py
git commit -m "feat: add code_execution tool wrapping RemoteExecutorService sandbox"
```

---

### Task 3: `tool_search` tool

**Files:**
- Create: `backend/tools/tool_search_tool.py`
- Test: `backend/tests/unit/test_tool_search_tool.py`
- Test: `backend/tests/integration/test_tool_search_registration.py`

**Interfaces:**
- Consumes: `backend.core.tool_registry.tool_registry.list_tools(tier)` → `{name: {description, parameters}}`; the registry instance is the lazy global `tool_registry`.
- Produces: `tool_search_tool.execute(action, **kwargs)` → dict; singleton `tool_search_tool`. `tier` defaults to caller's tier passed via `agent_id` (first char) or an explicit `tier` kwarg; results are always scoped to authorized tools only.

- [ ] **Step 1: Write the failing unit test**

```python
# backend/tests/unit/test_tool_search_tool.py
import asyncio
from backend.tools import tool_search_tool


def test_search_ranks_by_query():
    result = asyncio.get_event_loop().run_until_complete(
        tool_search_tool.execute("search", query="search the web", tier="0xxxx", limit=5)
    )
    assert result["status"] == "success"
    names = [r["name"] for r in result["results"]]
    assert "web_search" in names
    assert result["results"][0]["name"] == "web_search"


def test_get_returns_descriptor():
    result = asyncio.get_event_loop().run_until_complete(
        tool_search_tool.execute("get", name="web_search", tier="0xxxx")
    )
    assert result["status"] == "success"
    assert "description" in result


def test_empty_query_errors():
    result = asyncio.get_event_loop().run_until_complete(
        tool_search_tool.execute("search", query="   ", tier="0xxxx")
    )
    assert result["status"] == "error"


def test_help_action():
    result = asyncio.get_event_loop().run_until_complete(tool_search_tool.execute("help"))
    assert result["status"] == "success"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/unit/test_tool_search_tool.py -o addopts='' -q"`
Expected: ERROR/FAIL — `ModuleNotFoundError: backend.tools.tool_search_tool`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/tools/tool_search_tool.py
"""Tool Search Tool — runtime discovery of registered tools by capability.

Lets an agent find the right tool without being handed the entire tool list.
Scores the caller's authorized tools (via tool_registry.list_tools) by
token-overlap over name + description + parameter names, with a boost for
name/substring hits. In-memory scoring — no new vector store needed.
Registered in ToolRegistry as "tool_search", available to all tiers.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from backend.core.tool_registry import tool_registry

logger = logging.getLogger(__name__)


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9_]+", (text or "").lower()) if t]


class ToolSearchTool:
    TOOL_NAME = "tool_search"
    AUTHORIZED_TIERS = [f"{i}xxxx" for i in range(10)]

    def _resolve_tier(self, kwargs: Dict[str, Any]) -> str:
        if kwargs.get("tier"):
            return kwargs["tier"]
        aid = kwargs.get("agent_id") or ""
        return (aid[:1] + "xxxx") if aid else "0xxxx"

    def _score(self, query_tokens: List[str], name: str, desc: str, params: Dict) -> tuple:
        hay = _tokens(name) + _tokens(desc) + _tokens(" ".join(params.keys()))
        name_tokens = set(_tokens(name))
        overlap = len(set(query_tokens) & set(hay))
        name_hit = len(set(query_tokens) & name_tokens)
        score = overlap + 2.0 * name_hit
        reasons = []
        if name_hit:
            reasons.append(f"name match: {', '.join(set(query_tokens) & name_tokens)}")
        elif overlap:
            reasons.append("description/parameter match")
        return score, "; ".join(reasons) or "partial relevance"

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        if action == "help":
            return {
                "status": "success",
                "description": (
                    "Discover registered tools by describing what you need. Returns ranked "
                    "tool names + descriptions scoped to your tier. Full reference in "
                    "backend/.agentium/skills/tool_search/SKILL.md."
                ),
            }
        if action == "get":
            name = kwargs.get("name")
            if not name:
                return {"status": "error", "error": "name is required"}
            tier = self._resolve_tier(kwargs)
            available = tool_registry.list_tools(tier)
            if name not in available:
                return {"status": "error", "error": f"tool '{name}' not found / not authorized"}
            return {"status": "success", "name": name, **available[name]}

        if action != "search":
            return {"status": "error", "error": f"Unknown action: {action}"}

        query = (kwargs.get("query") or "").strip()
        if not query:
            return {"status": "error", "error": "query is required"}
        limit = int(kwargs.get("limit", 10))
        tier = self._resolve_tier(kwargs)
        available = tool_registry.list_tools(tier)
        q_tokens = _tokens(query)

        scored = []
        for name, desc in available.items():
            score, reason = self._score(
                q_tokens, name, desc.get("description", ""), desc.get("parameters", {})
            )
            if score > 0:
                scored.append({
                    "name": name,
                    "description": desc.get("description", ""),
                    "score": round(score, 2),
                    "match_reason": reason,
                })
        scored.sort(key=lambda r: r["score"], reverse=True)
        return {
            "status": "success",
            "query": query,
            "count": len(scored[:limit]),
            "results": scored[:limit],
        }


tool_search_tool = ToolSearchTool()
```

- [ ] **Step 4: Run unit test to verify it passes**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/unit/test_tool_search_tool.py -o addopts='' -q"`
Expected: PASS (4 passed)

- [ ] **Step 5: Write the registration test**

```python
# backend/tests/integration/test_tool_search_registration.py
from backend.core.tool_registry import tool_registry


def test_tool_search_registered():
    assert "tool_search" in tool_registry.tools
    tool = tool_registry.get_tool("tool_search")
    assert set(tool["authorized_tiers"]) == {f"{i}xxxx" for i in range(10)}


def test_tool_search_in_openai_all_tiers():
    for tier in [f"{i}xxxx" for i in range(10)]:
        names = [t["function"]["name"] for t in tool_registry.to_openai_tools(tier)]
        assert "tool_search" in names


def test_tool_search_required_param():
    props, required = tool_registry._build_props(tool_registry.get_tool("tool_search"))
    assert "query" in required
    assert "limit" not in required
```

- [ ] **Step 6: Run registration test**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/integration/test_tool_search_registration.py -o addopts='' -q"`
Expected: FAIL — `tool_search` not yet in registry (Task 4 wires it).

- [ ] **Step 7: Commit**

```bash
git add backend/tools/tool_search_tool.py backend/tests/unit/test_tool_search_tool.py backend/tests/integration/test_tool_search_registration.py
git commit -m "feat: add tool_search tool (runtime tool discovery by capability)"
```

---

### Task 4: Register the three tools in `tool_registry.py`

**Files:**
- Modify: `backend/core/tool_registry.py` (imports near top; three `register_tool` blocks in `_initialize_tools`)
- Test: re-run the three registration tests from Tasks 1–3.

**Interfaces:**
- Consumes: the three singletons `web_fetch_tool`, `code_execution_tool`, `tool_search_tool` (now importable after Tasks 1–3).
- Produces: `tool_registry.tools` now contains `web_fetch`, `code_execution`, `tool_search`; exported by `to_openai_tools`/`to_anthropic_tools` per their tiers.

- [ ] **Step 1: Add imports near the other tool imports (top of file, after line 30)**

Insert after the `from backend.tools.remote_exec_tool import execute as remote_exec_tool_execute` line:

```python
from backend.tools.web_fetch_tool     import web_fetch_tool
from backend.tools.code_execution_tool import code_execution_tool
from backend.tools.tool_search_tool    import tool_search_tool
```

- [ ] **Step 2: Add `web_fetch` registration block near the `web_search` block (after line 245)**

```python
        # ══════════════════════════════════════════════════════════════════════
        # WEB FETCH TOOL
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="web_fetch",
            description=(
                "Fetch a URL and return its content as clean Markdown with a token "
                "budget, so you can read a page without blowing your context window. "
                "Distinct from web_search (which returns result lists). Supports caching "
                "and domain allow-lists. Full reference in "
                "backend/.agentium/skills/web_fetch/SKILL.md."
            ),
            function=web_fetch_tool.execute,
            parameters={
                "action":         {"type": "string",  "description": "fetch | help"},
                "url":            {"type": "string",  "description": "URL to fetch"},
                "max_tokens":     {"type": "integer", "description": "Truncate returned Markdown to ~this token budget (default 4000)", "optional": True},
                "use_cache":      {"type": "boolean", "description": "Serve cached result if <5 min old (default true)", "optional": True},
                "allowed_domains":{"type": "array",   "description": "If set, only these domains are permitted", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx", "7xxxx", "8xxxx", "9xxxx"],
        )
```

- [ ] **Step 3: Add `code_execution` registration block (after the remote_exec_tool / remote execution area, near line 30 module; place it after the `web_fetch` block for locality)**

```python
        # ══════════════════════════════════════════════════════════════════════
        # CODE EXECUTION TOOL
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="code_execution",
            description=(
                "Execute code in an isolated Docker sandbox (brains vs hands). Raw data "
                "never leaves the sandbox — you receive only a structured summary. Use for "
                "computation, data transforms, or running snippets safely. Distinct from "
                "execute_command (shell). Restricted to 0xxxx/1xxxx/2xxxx. Full reference "
                "in backend/.agentium/skills/code_execution/SKILL.md."
            ),
            function=code_execution_tool.execute,
            parameters={
                "action":         {"type": "string", "description": "execute | help"},
                "code":           {"type": "string", "description": "Source code to run (default language python)"},
                "language":       {"type": "string", "description": "Language (default python)", "optional": True},
                "dependencies":   {"type": "array",  "description": "pip packages to install in the sandbox", "optional": True},
                "input_data":     {"type": "any",    "description": "Input data exposed to code as input_data", "optional": True},
                "timeout_seconds":{"type": "integer","description": "Execution timeout (default 300)", "optional": True},
                "network_access": {"type": "boolean","description": "Allow outbound network in sandbox (default false)", "optional": True},
                "agent_id":       {"type": "string", "description": "Caller agentium id, used for tier authorization", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
```

- [ ] **Step 4: Add `tool_search` registration block (after the `code_execution` block)**

```python
        # ══════════════════════════════════════════════════════════════════════
        # TOOL SEARCH TOOL
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="tool_search",
            description=(
                "Discover registered tools by describing what you need. Returns ranked "
                "tool names + descriptions scoped to your tier, so you can find the right "
                "tool without being handed the entire tool list. Use 'get' to fetch one "
                "tool's full descriptor. Full reference in "
                "backend/.agentium/skills/tool_search/SKILL.md."
            ),
            function=tool_search_tool.execute,
            parameters={
                "action":  {"type": "string", "description": "search | get | help"},
                "query":   {"type": "string", "description": "Natural-language need / capability phrase (search action)"},
                "name":    {"type": "string", "description": "Tool name to retrieve (get action)", "optional": True},
                "limit":   {"type": "integer","description": "Max results (default 10)", "optional": True},
                "tier":    {"type": "string", "description": "Tier whose tools to search; defaults to caller tier", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx", "7xxxx", "8xxxx", "9xxxx"],
        )
```

- [ ] **Step 5: Run all three registration tests**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/integration/test_web_fetch_registration.py tests/integration/test_code_execution_registration.py tests/integration/test_tool_search_registration.py -o addopts='' -q"`
Expected: PASS (all).

- [ ] **Step 6: Smoke test that the registry imports cleanly**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && python -c \"from backend.core.tool_registry import tool_registry; print(sorted(t for t in ['web_fetch','code_execution','tool_search'] if t in tool_registry.tools)))\""`
Expected: `['code_execution', 'tool_search', 'web_fetch']`

- [ ] **Step 7: Commit**

```bash
git add backend/core/tool_registry.py
git commit -m "feat: register web_fetch, code_execution, tool_search in ToolRegistry"
```

---

### Task 5: Author and seed the three `SKILL.md` files

**Files:**
- Create: `backend/.agentium/skills/web_fetch/SKILL.md`
- Create: `backend/.agentium/skills/code_execution/SKILL.md`
- Create: `backend/.agentium/skills/tool_search/SKILL.md`
- Test: `backend/tests/unit/test_skill_seeding_tool_audit.py`

**Interfaces:**
- Consumes: `backend.scripts.seed_skills` (`parse_skill_file(path)` returns `SkillSchema`; `main()` indexes `backend/.agentium/skills/`).
- Produces: three skills indexed into ChromaDB, discoverable via `SkillManager.search_skills`.

- [ ] **Step 1: Write `backend/.agentium/skills/web_fetch/SKILL.md`**

```markdown
---
name: web_fetch
description: >-
  Fetch a URL and return its page content as clean Markdown with a token budget,
  so an agent can read a web page without burning context. Use the web_fetch tool
  when you have a specific URL and need its content (not search results). Skill
  file at backend/.agentium/skills/web_fetch/SKILL.md.
skill_type: research
domain: general
complexity: beginner
tags: [web, fetch, scraping, markdown, retrieval]
creator_tier: head
---

# Web Fetch

Retrieve the contents of a specific URL as Markdown.

## Steps
1. Call the `web_fetch` tool with `action="fetch"` and the target `url`.
2. Set `max_tokens` to keep the returned Markdown within your context budget.
3. Enable `use_cache` (default) to avoid re-fetching within 5 minutes.
4. Pass `allowed_domains` to restrict fetches to trusted hosts.

## Validation
- The tool returns `status: success` with `markdown`, `title`, and `token_count`.
- Oversized pages are truncated and flagged with `truncated: true`.
- Failures return `status: error` without raising into the agent context.
```

- [ ] **Step 2: Write `backend/.agentium/skills/code_execution/SKILL.md`**

```markdown
---
name: code_execution
description: >-
  Run code in an isolated Docker sandbox via the code_execution tool. Raw data
  never leaves the sandbox; you receive only a structured summary. Use for safe
  computation, data transforms, or running untrusted snippets. Restricted to
  0xxxx/1xxxx/2xxxx tiers. Skill file at
  backend/.agentium/skills/code_execution/SKILL.md.
skill_type: automation
domain: backend
complexity: intermediate
tags: [code, sandbox, execution, docker, computation]
creator_tier: head
---

# Code Execution

Execute code safely inside the existing Docker sandbox.

## Steps
1. Call the `code_execution` tool with `action="execute"` and your `code`.
2. Set `language` (default python) and `dependencies` for pip packages.
3. Pass `input_data` to make data available to the code as `input_data`.
4. Enable `network_access` only when the snippet must reach the network.

## Validation
- The tool returns the sandbox summary (`status`, `summary`, `execution_time_ms`).
- Disallowed or insecure code is blocked by the execution guard (`status: blocked`).
- Raw output never enters agent context.
```

- [ ] **Step 3: Write `backend/.agentium/skills/tool_search/SKILL.md`**

```markdown
---
name: tool_search
description: >-
  Discover registered Agentium tools by describing what you need, using the
  tool_search tool. Returns ranked tool names and descriptions scoped to your
  tier, so you can find the right tool without seeing the entire tool list. Use
  the get action to fetch one tool's full descriptor. Skill file at
  backend/.agentium/skills/tool_search/SKILL.md.
skill_type: integration
domain: ai
complexity: beginner
tags: [discovery, tools, registry, search]
creator_tier: head
---

# Tool Search

Find the right tool at runtime by capability.

## Steps
1. Call `tool_search` with `action="search"` and a `query` describing the need.
2. Read the ranked `results` to pick a tool.
3. Call `action="get"` with the chosen `name` to retrieve its full descriptor.

## Validation
- `search` returns `status: success` with ranked `results` (name, description, score).
- `get` returns the tool's `description` and `parameters`, or an error if not authorized.
- Results are always scoped to tools your tier may use.
```

- [ ] **Step 4: Write the seeding test**

```python
# backend/tests/unit/test_skill_seeding_tool_audit.py
from pathlib import Path
from backend.scripts.seed_skills import parse_skill_file


def test_three_skills_parse():
    base = Path("backend/.agentium/skills")
    for name in ["web_fetch", "code_execution", "tool_search"]:
        p = base / name / "SKILL.md"
        assert p.exists(), f"missing {p}"
        schema = parse_skill_file(p)
        assert schema.name == name
        assert 50 <= len(schema.description) <= 300
        assert schema.skill_type in {
            "code_generation", "analysis", "integration", "automation",
            "research", "design", "testing", "deployment", "debugging",
            "optimization", "documentation",
        }
        assert schema.domain in {
            "frontend", "backend", "devops", "data", "ai", "security",
            "mobile", "desktop", "general", "database", "api",
        }
```

- [ ] **Step 5: Run the seeding test**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/unit/test_skill_seeding_tool_audit.py -o addopts='' -q"`
Expected: PASS.

- [ ] **Step 6: Seed the skills into ChromaDB**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && PYTHONPATH=. python scripts/seed_skills.py"`
Expected: no error; three new skills indexed (look for `web_fetch`/`code_execution`/`tool_search` in output).

- [ ] **Step 7: Commit**

```bash
git add backend/.agentium/skills/web_fetch/SKILL.md backend/.agentium/skills/code_execution/SKILL.md backend/.agentium/skills/tool_search/SKILL.md backend/tests/unit/test_skill_seeding_tool_audit.py
git commit -m "feat: add SKILL.md for web_fetch, code_execution, tool_search"
```

---

### Task 6: Full verification and acceptance check

**Files:** none new — verification only.

**Interfaces:** n/a.

- [ ] **Step 1: Run all unit tests for the three tools + skills**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/unit/test_web_fetch_tool.py tests/unit/test_code_execution_tool.py tests/unit/test_tool_search_tool.py tests/unit/test_skill_seeding_tool_audit.py -o addopts='' -q"`
Expected: all PASS.

- [ ] **Step 2: Run all integration registration tests**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/integration/test_web_fetch_registration.py tests/integration/test_code_execution_registration.py tests/integration/test_tool_search_registration.py -o addopts='' -q"`
Expected: all PASS.

- [ ] **Step 3: Verify tier gating end-to-end via the registry**

Run: `docker compose exec -T backend bash -lc "cd /app/backend && python -c \"
from backend.core.tool_registry import tool_registry
for t in ['0xxxx','3xxxx','7xxxx']:
    names=[x['function']['name'] for x in tool_registry.to_openai_tools(t)]
    print(t, 'code_execution' in names, 'web_fetch' in names, 'tool_search' in names)
\""`
Expected:
```
0xxxx True True True
3xxxx False True True
7xxxx False True True
```

- [ ] **Step 4: Commit a final verification note (no code change) — only if any fix was required**

If Steps 1–3 all passed unchanged, skip. Otherwise fix, re-run, and commit the fix with message `fix: <what was fixed> for tool audit gap tools`.

---

## Self-Review Notes (per skill checklist)

- **Spec coverage:** §3.1 web_fetch ✓ (Task 1), §3.2 code_execution ✓ (Task 2), §3.3 tool_search ✓ (Task 3), §4 registration ✓ (Task 4), §5 skills ✓ (Task 5), §6 testing ✓ (Tasks 1–5), §7 safety ✓ (encoded in each tool's error handling and tier gates), §8 acceptance ✓ (Task 6).
- **Placeholder scan:** no TBD/TODO; every step has concrete code or commands.
- **Type consistency:** `execute(action, **kwargs)` signature used identically across all three tools and tests; `RemoteExecutorService.execute` kwargs match Task 2's call; `tool_registry.list_tools(tier)` return shape (`{name: {description, parameters}}`) matches Task 3's consumption; `register_tool` param shape matches existing blocks.
- **Tier gating:** enforced solely via `authorized_tiers` (confirmed `to_openai_tools`/`to_anthropic_tools` filter on it), no conflict with `restricted_tools_for`.
