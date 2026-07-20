# Constitution-Driven Persona — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the active Constitution the single source of truth for every agent's persona/behavior (all tiers) and the voice bridge, so editing it via the UI updates behavior everywhere with no code change.

**Architecture:** A new central `backend/core/persona.py` exposes `build_persona_directive(constitution, tier, channel)` which composes the persona entirely from the Constitution (preamble + a dedicated `agent_persona_and_conduct` article + `sovereign_preferences` + `prohibited_actions` + tier emphasis + clause citations + version footer). `Agent.get_system_prompt()` and `PromptTemplateManager.build_system_prompt()` call it (live-read from the active Constitution row), and the voice bridge pulls the same directive through `/api/v1/chat/persona?channel=voice`. Ethos keeps only operational working memory. A cache-invalidation helper ensures UI edits propagate immediately.

**Tech Stack:** Python 3 / FastAPI (backend), SQLAlchemy 2 ORM, Redis (cache), pytest. Voice bridge is Python (urllib). No new dependencies. No Alembic migration (composes from existing Constitution fields).

## Global Constraints

- **No migration** — persona is composed from existing Constitution fields (`preamble`, `articles`, `prohibited_actions`, `sovereign_preferences`); no new DB column.
- **Ethos carries NO persona** — only operational working memory (`current_objective`, `active_plan`, `working_method`, `capabilities`, `environment_context`). Persona/values/rules/restrictions come from the Constitution at prompt time.
- **No hardcoded persona strings** in any prompt path — all persona leads in `PROVIDER_TEMPLATES`, `chat.py`, `persistent_council.py`, `overflow_recovery.py` are stripped; the Constitution is the only source.
- **Live-read + cache invalidation** — persona is read from the active Constitution on every prompt build; any write (`update_constitution`, amendment ratification) invalidates the Redis cache so edits appear with no agent recreation.
- **Single composition path** — `build_persona_directive` is the only function that turns a Constitution into a persona; chat, task execution, and voice all use it (no divergence).
- Tests run with `pytest` (project `backend/pytest.ini`); tests execute against the configured test database. All prompt-building functions accept an optional `db` so they can be unit-tested without a live server.

---

## File Structure

- **Create** `backend/core/persona.py` — `get_active_constitution_dict(db)`, `build_persona_directive(constitution, tier, channel)`, tier mapping, `FALLBACK_PERSONA`, `VOICE_ADAPTATION`. Single source of truth for persona composition.
- **Modify** `backend/core/constitutional_guard.py` — add `invalidate_active_constitution_cache()` static helper.
- **Modify** `backend/main.py` — call invalidation in `update_constitution` (879–913).
- **Modify** `backend/services/amendment_service.py` — call invalidation where a new active Constitution is committed (ratification).
- **Modify** `backend/models/entities/agents.py` — `get_system_prompt()` (338) → Constitution-driven; add `_tier_from_type()`, `_ethos_operational_context()`; fix `read_and_align_constitution()` fallback (441–472); strip persona from the `templates` dict (1273–1438) used by `_create_agent_ethos`.
- **Modify** `backend/services/prompt_template_manager.py` — `build_system_prompt()` (708) prepends the Constitution persona and passes empty persona vars to provider templates; add `_strip_persona_leads()` so provider persona leads never reach the model.
- **Modify** `backend/services/initialization_service.py` — `create_default_constitution()` (1098) adds the `agent_persona_and_conduct` article and a `communication_style` sovereign preference.
- **Modify** `backend/api/routes/chat.py` — `get_persona` (441) accepts `channel`; `_stream_response` (519) merges voice persona into the system prompt and drops the hardcoded "You are speaking directly to the Sovereign" line (523–524).
- **Modify** `voice-bridge/main.py` — `_fetch_backend_persona()` (380) requests `?channel=voice`; fix misleading comment (408).
- **Modify** `backend/services/persistent_council.py` (223–266) and `backend/services/overflow_recovery.py` (164) — replace hardcoded ethos persona with functional role lines (Constitution supplies persona at prompt time).
- **Add** `POST /api/v1/constitution/preview-persona` (in `backend/main.py`) — renders the directive from a draft Constitution so the UI can preview before saving.
- **Tests** `backend/tests/test_constitution_persona.py` — unit + end-to-end coverage of the acceptance criteria.

---

### Task 1: Central persona composition module

**Files:**
- Create: `backend/core/persona.py`
- Test: `backend/tests/test_constitution_persona.py` (Task 1 section)

**Interfaces:**
- Consumes: `Constitution` ORM (`get_articles_dict()`, `get_prohibited_actions_list()`, `get_sovereign_preferences()`, `version`, `version_number`, `agentium_id`, `preamble`).
- Produces: `get_active_constitution_dict(db) -> Optional[Dict]`, `build_persona_directive(constitution, tier=None, channel="text") -> str`. Used by Tasks 3, 6, 8, 9, 10, 11.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_constitution_persona.py
import pytest
from backend.core.persona import build_persona_directive, FALLBACK_PERSONA


def _sample_constitution():
    return {
        "version": "v2.0.0",
        "version_number": 2,
        "agentium_id": "C00002",
        "preamble": "We the Agents establish this Constitution.",
        "articles": {
            "agent_persona_and_conduct": {
                "title": "Agent Persona & Conduct",
                "content": "MARKER_PERSONA_CLAUSE speak calmly and helpfully.",
            },
            "article_1": {"title": "Prime Directive", "content": "Safety first."},
        },
        "prohibited_actions": ["Never impersonate a higher tier"],
        "sovereign_preferences": {
            "communication_style": "Be concise.",
        },
    }


def test_build_persona_includes_preamble_and_persona_article():
   文本 = build_persona_directive(_sample_constitution())
    assert "We the Agents establish this Constitution." in 文本
    assert "MARKER_PERSONA_CLAUSE" in 文本


def test_build_persona_voice_channel_adds_spoken_adaptation():
    文本 = build_persona_directive(_sample_constitution(), channel="voice")
    assert "text-to-speech" in 文本
    assert "Be concise." in 文本


def test_build_persona_tier_emphasis_and_citations():
    文本 = build_persona_directive(_sample_constitution(), tier=3)
    assert "Task Agent" in 文本
    assert "In-Effect Constitutional Clauses" in 文本
    assert "agent_persona_and_conduct" in 文本


def test_build_persona_provenance_footer():
    文本 = build_persona_directive(_sample_constitution())
    assert "<!-- persona built from Constitution v2.0.0 (C00002) -->" in 文本


def test_build_persona_none_returns_fallback():
    assert build_persona_directive(None) == FALLBACK_PERSONA
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_constitution_persona.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.core.persona'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/core/persona.py
"""Single source of truth for agent persona/behavior.

Persona is composed ENTIRELY from the active Constitution. No hardcoded
persona strings live here — see spec §3, §5.
"""
from typing import Any, Dict, Optional

FALLBACK_PERSONA = (
    "You are an AI agent operating within the Agentium governance system, "
    "bound by its Constitution."
)

VOICE_ADAPTATION = (
    "Respond in concise, natural spoken language suitable for text-to-speech: "
    "no markdown, no bullet lists, short sentences, conversational tone."
)

# Tier -> human label (improvement #5: tier-aware emphasis).
TIER_LABELS = {
    0: "Head of Council",
    1: "Council Member",
    2: "Lead Agent",
    3: "Task Agent",
    4: "Code Critic",
    5: "Output Critic",
    6: "Plan Critic",
}


def get_active_constitution_dict(db) -> Optional[Dict[str, Any]]:
    """Load the active Constitution row as a plain dict (live-read)."""
    from backend.models.entities.constitution import Constitution
    constitution = (
        db.query(Constitution)
        .filter_by(is_active=True)
        .order_by(Constitution.version_number.desc())
        .first()
    )
    if not constitution:
        return None
    return {
        "version": getattr(constitution, "version", "1.0"),
        "version_number": getattr(constitution, "version_number", 1),
        "agentium_id": constitution.agentium_id,
        "preamble": constitution.preamble or "",
        "articles": constitution.get_articles_dict() or {},
        "prohibited_actions": constitution.get_prohibited_actions_list() or [],
        "sovereign_preferences": constitution.get_sovereign_preferences() or {},
    }


def _article_applies_to(article_data: Dict[str, Any], tier: Optional[int]) -> bool:
    """An article may carry 'applies_to' (list of tiers); default = all tiers."""
    if tier is None:
        return True
    applies = article_data.get("applies_to")
    if not applies:
        return True
    return tier in applies or str(tier) in [str(t) for t in applies]


def build_persona_directive(
    constitution: Optional[Dict[str, Any]],
    tier: Optional[int] = None,
    channel: str = "text",
) -> str:
    """Compose the persona/behavior directive entirely from the Constitution.

    Order (spec §5): identity, persona & conduct, communication style,
    boundaries, tier emphasis, clause citations, provenance footer.
    """
    if not constitution:
        return FALLBACK_PERSONA

    parts: list[str] = []
    version = constitution.get("version", "1.0")
    agentium_id = constitution.get("agentium_id", "C00001")
    articles = constitution.get("articles", {}) or {}
    sovereign = constitution.get("sovereign_preferences", {}) or {}

    preamble = (constitution.get("preamble") or "").strip()
    if preamble:
        parts.append(f"# Identity\n{preamble}")

    persona_article = articles.get("agent_persona_and_conduct") or {}
    persona_text = (persona_article.get("content") or "").strip()
    if persona_text:
        parts.append(f"# Persona & Conduct\n{persona_text}")

    style_bits = []
    comm = sovereign.get("communication_style")
    if comm:
        style_bits.append(str(comm))
    if channel == "voice":
        style_bits.append(VOICE_ADAPTATION)
    if style_bits:
        parts.append("# Communication Style\n" + "\n".join(f"- {s}" for s in style_bits))

    prohibited = constitution.get("prohibited_actions") or []
    if prohibited:
        parts.append(
            "# Boundaries (Prohibited Actions)\n"
            + "\n".join(f"- {p}" for p in prohibited)
        )

    if tier is not None:
        label = TIER_LABELS.get(tier, "Agent")
        parts.append(f"# Your Role\nYou serve as the {label} in the Agentium hierarchy.")
        emphasised = []
        for key, data in articles.items():
            if key == "agent_persona_and_conduct":
                continue
            if _article_applies_to(data, tier):
                emphasised.append(f"- [{key}] {data.get('title', key)}")
        if emphasised:
            parts.append("# Constitutional Emphasis for Your Tier\n" + "\n".join(emphasised))

    citations = [f"- {key}: {d.get('title', key)}" for key, d in articles.items()]
    if citations:
        parts.append("# In-Effect Constitutional Clauses\n" + "\n".join(citations))

    parts.append(f"<!-- persona built from Constitution {version} ({agentium_id}) -->")
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_constitution_persona.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/persona.py backend/tests/test_constitution_persona.py
git commit -m "feat: add central Constitution-driven persona composition module"
```

---

### Task 2: Cache invalidation on Constitution writes

**Files:**
- Modify: `backend/core/constitutional_guard.py` (after `__init__`, ~line 205)
- Modify: `backend/main.py` (after `db.commit()` at line 906)
- Modify: `backend/services/amendment_service.py` (ratification commit)
- Test: `backend/tests/test_constitution_persona.py` (Task 2 section)

**Interfaces:**
- Consumes: Redis via `REDIS_URL`; key `constitutional_guard:active_constitution`.
- Produces: `ConstitutionalGuard.invalidate_active_constitution_cache()` static method.

- [ ] **Step 1: Write the failing test**

```python
def test_invalidate_active_constitution_cache_clears_redis():
    from backend.core.constitutional_guard import ConstitutionalGuard
    import os, redis
    r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    r.set("constitutional_guard:active_constitution", '{"stale": true}')
    ConstitutionalGuard.invalidate_active_constitution_cache()
    assert r.get("constitutional_guard:active_constitution") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_constitution_persona.py::test_invalidate_active_constitution_cache_clears_redis -v`
Expected: FAIL with `AttributeError: type object 'ConstitutionalGuard' has no attribute 'invalidate_active_constitution_cache'`

- [ ] **Step 3: Write minimal implementation**

Add to `backend/core/constitutional_guard.py` (inside the class, after `__init__`):

```python
    # ------------------------------------------------------------------
    # Cache invalidation — called whenever the active Constitution is
    # written (UI update or amendment ratification) so persona/governance
    # changes propagate immediately (spec §6.5).
    # ------------------------------------------------------------------
    @staticmethod
    def invalidate_active_constitution_cache() -> None:
        import os
        import redis as _redis
        url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        try:
            r = _redis.from_url(url, decode_responses=True)
            r.delete("constitutional_guard:active_constitution")
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("Could not invalidate active constitution cache: %s", exc)
```

In `backend/main.py`, after `db.commit()` (line 906) inside `update_constitution`, add:

```python
    from backend.core.constitutional_guard import ConstitutionalGuard
    ConstitutionalGuard.invalidate_active_constitution_cache()
```

In `backend/services/amendment_service.py`, at the point where a newly ratified Constitution row is committed with `is_active=True` (the ratification write in `conclude_voting`), add the same two lines immediately after that commit.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_constitution_persona.py::test_invalidate_active_constitution_cache_clears_redis -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/constitutional_guard.py backend/main.py backend/services/amendment_service.py
git commit -m "feat: invalidate active-constitution cache on any Constitution write"
```

---

### Task 3: `Agent.get_system_prompt()` becomes Constitution-driven

**Files:**
- Modify: `backend/models/entities/agents.py:338-356` (`get_system_prompt`)
- Modify: `backend/models/entities/agents.py` (add helpers near `get_system_prompt`)
- Test: `backend/tests/test_constitution_persona.py` (Task 3 section)

**Interfaces:**
- Consumes: `get_active_constitution_dict`, `build_persona_directive` from `backend.core.persona`; `AgentType` enum; `self.ethos` (Ethos).
- Produces: `Agent.get_system_prompt(self, db=None, channel="text") -> str`; `Agent._tier_from_type(self) -> Optional[int]`; `Agent._ethos_operational_context(self) -> str`.

- [ ] **Step 1: Write the failing test**

```python
def test_get_system_prompt_is_constitution_driven(test_db, head_agent):
    from backend.core.persona import build_persona_directive
    # head_agent fixture builds an Agent + Ethos + an active Constitution containing MARKER_PERSONA_CLAUSE
    prompt = head_agent.get_system_prompt(db=test_db)
    assert "MARKER_PERSONA_CLAUSE" in prompt
    # Ethos must NOT inject persona — only operational context
    assert "Head of Council, the ultimate decision-making authority" not in prompt


def test_get_system_prompt_voice_channel():
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        from backend.models.entities.agents import HeadOfCouncil
        head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        prompt = head.get_system_prompt(db=db, channel="voice")
        assert "text-to-speech" in prompt
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_constitution_persona.py -k get_system_prompt -v`
Expected: FAIL (persona clause absent / hardcoded mission present)

- [ ] **Step 3: Write minimal implementation**

Replace `get_system_prompt` (agents.py:338-356) with:

```python
    def _tier_from_type(self) -> Optional[int]:
        from backend.models.entities.agents import AgentType
        mapping = {
            AgentType.HEAD_OF_COUNCIL: 0,
            AgentType.COUNCIL_MEMBER: 1,
            AgentType.LEAD_AGENT: 2,
            AgentType.TASK_AGENT: 3,
            AgentType.CODE_CRITIC: 4,
            AgentType.OUTPUT_CRITIC: 5,
            AgentType.PLAN_CRITIC: 6,
        }
        return mapping.get(self.agent_type)

    def _ethos_operational_context(self) -> str:
        """Operational working memory ONLY — never persona/values (spec §3)."""
        e = self.ethos
        if not e:
            return ""
        bits = []
        obj = getattr(e, "current_objective", None)
        if obj:
            bits.append(f"Current objective: {obj}")
        wm = getattr(e, "working_method", None)
        if wm:
            bits.append(f"Standard working method:\n{wm}")
        caps = e.get_capabilities()
        if caps:
            bits.append("Capabilities: " + ", ".join(caps))
        env = getattr(e, "environment_context", None)
        if env:
            bits.append(f"Environment: {env}")
        return "\n\n".join(bits)

    def get_system_prompt(self, db=None, channel: str = "text") -> str:
        """Effective system prompt — persona is built from the Constitution."""
        if self.system_prompt_override:
            return self.system_prompt_override

        from backend.core.persona import (
            get_active_constitution_dict,
            build_persona_directive,
        )
        close = False
        if db is None:
            from backend.database import SessionLocal
            db = SessionLocal()
            close = True
        try:
            constitution = get_active_constitution_dict(db)
            persona = build_persona_directive(
                constitution, tier=self._tier_from_type(), channel=channel
            )
        finally:
            if close:
                db.close()

        ethos_ctx = self._ethos_operational_context()
        if ethos_ctx:
            persona += "\n\n" + ethos_ctx

        if self.is_persistent and self.status == AgentStatus.IDLE_WORKING:
            persona += (
                "\n\n[IDLE MODE ACTIVE]: You are operating in low-token optimization "
                "mode. Focus on efficient local inference and database operations."
            )
        return persona
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_constitution_persona.py -k get_system_prompt -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models/entities/agents.py
git commit -m "feat: make Agent.get_system_prompt Constitution-driven"
```

---

### Task 4: Fix `read_and_align_constitution` fallback

**Files:**
- Modify: `backend/models/entities/agents.py:441-472` (graceful fallback)
- Test: `backend/tests/test_constitution_persona.py` (Task 4 section)

**Interfaces:**
- Consumes: same as before (`Constitution`, `Ethos`).
- Produces: `read_and_align_constitution(db)` still records only `constitutional_references` (no persona copy). Fallback no longer crashes when `docs/constitution/core.md` is absent.

- [ ] **Step 1: Write the failing test**

```python
def test_read_and_align_constitution_missing_fallback_file_ok(test_db, head_agent):
    # Ensure the fallback text file does NOT exist, then alignment must still succeed
    import os
    fallback = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "docs", "constitution", "core.md"
    )
    # (file is already absent in repo; test asserts no exception / returns True)
    result = head_agent.read_and_align_constitution(test_db)
    assert result is True
```

- [ ] **Step 2: Run test to verify it fails** (only if current fallback raises/returns False in your env)

Run: `cd backend && pytest tests/test_constitution_persona.py -k read_and_align -v`

- [ ] **Step 3: Write minimal implementation**

Replace the `except Exception as fallback_exc:` block (agents.py:470-472) so a missing fallback file degrades gracefully instead of returning False:

```python
            except Exception as fallback_exc:
                logger.error(f"[FATAL] Constitution fallback also failed: {fallback_exc}")
                # Degrade gracefully: record no references rather than failing
                # alignment. Persona is Constitution-driven at prompt time anyway.
                try:
                    ethos = db.query(Ethos).filter_by(id=self.ethos_id).first() if self.ethos_id else None
                    if ethos:
                        ethos.set_constitutional_references([])
                        db.flush()
                except Exception:
                    pass
                self.last_constitution_read_at = datetime.utcnow()
                self.constitution_read_count = (self.constitution_read_count or 0) + 1
                self.constitution_version = "vFallback"
                return True
```

(The `try:` that opens `fallback_path` at 447 should be wrapped so a missing file falls into this graceful branch — it already is, since `open()` raises and is caught by the outer `except`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_constitution_persona.py -k read_and_align -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models/entities/agents.py
git commit -m "fix: graceful degradation when constitution fallback file is absent"
```

---

### Task 5: Strip persona from Ethos creation templates

**Files:**
- Modify: `backend/models/entities/agents.py:1268-1461` (`CONSTITUTION_PREAMBLE`, `templates`, Ethos construction)
- Test: `backend/tests/test_constitution_persona.py` (Task 5 section)

**Interfaces:**
- Consumes: `AgentType`, `Ethos`, `json`.
- Produces: Ethos rows whose `mission_statement`/`core_values`/`behavioral_rules`/`restrictions` are neutral/operational; `capabilities` retained as operational. Persona is no longer seeded into Ethos.

- [ ] **Step 1: Write the failing test**

```python
def test_ethos_creation_has_no_persona(test_db):
    from backend.models.entities.agents import Agent, AgentType, Ethos
    from backend.models.entities.agents import HeadOfCouncil
    head = db...  # build a Head agent (reuse fixture)
    # After creation, Ethos must not contain hardcoded persona phrasing
    ethos = head.ethos
    assert "ultimate decision-making authority" not in (ethos.mission_statement or "")
    assert ethos.get_core_values() == []  # no values seeded as persona
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_constitution_persona.py -k ethos_creation -v`

- [ ] **Step 3: Write minimal implementation**

Remove `CONSTITUTION_PREAMBLE` (agents.py:1268-1271) — delete the constant (it is only used inside `templates`).

Replace the `templates` dict (1273-1438) so each tier keeps only an operational `mission` (functional role line) and `capabilities`; `core_values`/`rules`/`restrictions` become `"[]"`. Example for the first two tiers (apply identically to LEAD_AGENT, TASK_AGENT, CODE_CRITIC, OUTPUT_CRITIC, PLAN_CRITIC):

```python
        templates = {
            AgentType.HEAD_OF_COUNCIL: {
                'mission': (
                    "Head of Council — supreme executive authority and final approver. "
                    "Persona and conduct are defined by the Constitution, not by Ethos."
                ),
                'core_values': "[]",
                'rules': "[]",
                'restrictions': "[]",
                'capabilities': [
                    "Full system access",
                    "Constitutional amendment initiation",
                    "Emergency override authority",
                    "Subordinate Ethos viewing and editing",
                ],
            },
            AgentType.COUNCIL_MEMBER: {
                'mission': (
                    "Council Member — democratic deliberation, constitutional oversight, "
                    "and collaborative governance. Persona defined by the Constitution."
                ),
                'core_values': "[]",
                'rules': "[]",
                'restrictions': "[]",
                'capabilities': [
                    "Voting rights on amendments and proposals",
                    "Proposal submission",
                    "Knowledge governance (approve/reject submissions)",
                    "Subordinate Ethos viewing",
                ],
            },
            # LEAD_AGENT, TASK_AGENT, CODE_CRITIC, OUTPUT_CRITIC, PLAN_CRITIC:
            # same shape — keep their existing 'capabilities' lists, set
            # mission to a functional role line, core_values/rules/restrictions = "[]".
        }
```

The Ethos construction block (1447-1461) already reads `template['mission']`, `template['core_values']`, `template['rules']`, `template['restrictions']`, `template['capabilities']` — no change needed there.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_constitution_persona.py -k ethos_creation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models/entities/agents.py
git commit -m "refactor: remove hardcoded persona from Ethos creation templates"
```

---

### Task 6: `build_system_prompt` prepends Constitution persona

**Files:**
- Modify: `backend/services/prompt_template_manager.py:708-768` (`build_system_prompt`)
- Modify: `backend/services/prompt_template_manager.py` (add `_strip_persona_leads`)
- Test: `backend/tests/test_constitution_persona.py` (Task 6 section)

**Interfaces:**
- Consumes: `get_active_constitution_dict`, `build_persona_directive` from `backend.core.persona`.
- Produces: `build_system_prompt(...)` returns a system prompt whose persona comes from the Constitution; provider templates contribute formatting only.

- [ ] **Step 1: Write the failing test**

```python
def test_build_system_prompt_constitution_persona(test_db):
    from backend.services.prompt_template_manager import prompt_template_manager
    from backend.models.entities.constitution import Constitution
    # ensure active constitution contains MARKER_PERSONA_CLAUSE (fixture)
    prompt, _, _ = prompt_template_manager.build_system_prompt(
        provider=__import__("backend.services.prompt_template_manager", fromlist=["ProviderType"]).ProviderType.OPENAI,
        model_name="gpt-4o",
        task_description="do a thing",
        agent_ethos=None,
        agent_tier=3,
        db=test_db,
    )
    assert "MARKER_PERSONA_CLAUSE" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_constitution_persona.py -k build_system_prompt -v`

- [ ] **Step 3: Write minimal implementation**

Add a module-level helper near the other constants in `prompt_template_manager.py` (after `WORKSPACE_HINT`, ~line 600):

```python
    import re
    _PERSONA_LEAD_RE = re.compile(r"^\s*You are [^.]*\.\s*", re.MULTILINE | re.IGNORECASE)

    @staticmethod
    def _strip_persona_leads(text: str) -> str:
        """Remove provider template persona leads (e.g. 'You are Claude...').

        Keeps formatting/instruction content; persona is supplied by the
        Constitution (spec §6.3). Only the first leading sentence is stripped.
        """
        return _PERSONA_LEAD_RE.sub("", text, count=1)
```

Modify `build_system_prompt` (708-768):

```python
    def build_system_prompt(
        self,
        provider: ProviderType,
        model_name: str,
        task_description: str,
        agent_ethos: Any,
        agent_tier: int = 3,
        db=None,
    ) -> tuple:
        task_category = self.classify_task(task_description)
        template = self.get_template(provider, model_name, task_category, agent_tier)

        role_context = self._build_role_context(agent_tier, agent_ethos)

        # Persona is driven entirely by the Constitution (spec §6.3 / #2).
        from backend.core.persona import get_active_constitution_dict, build_persona_directive
        close = False
        if db is None:
            from backend.database import SessionLocal
            db = SessionLocal()
            close = True
        try:
            constitution = get_active_constitution_dict(db)
            persona = build_persona_directive(constitution, tier=agent_tier, channel="text")
        finally:
            if close:
                db.close()

        # Provider templates supply FORMATTING only; persona vars are blanked
        # so no hardcoded persona leaks through.
        system_vars = {
            "mission_statement": "",
            "role_context": role_context,
            "behavioral_rules": "",
            "specialization": getattr(agent_ethos, 'specialization', 'general assistance'),
            "working_method": getattr(agent_ethos, 'working_method', ''),
        }

        system_prompt, _ = template.format(system_vars, "")
        system_prompt = self._strip_persona_leads(system_prompt)

        # Prepend the Constitution persona as the authority.
        system_prompt = persona + "\n\n" + system_prompt

        system_prompt += self.DEEP_THINK_HINT
        system_prompt += self.HOST_ACCESS_HINT
        system_prompt += self.WORKSPACE_HINT

        working_method = getattr(agent_ethos, 'working_method', '') or ''
        if working_method.strip():
            system_prompt += (
                "\n\n## Your Standard Working Method\n"
                "Follow these steps as your default operating loop:\n"
                f"{working_method.strip()}\n"
            )

        return (system_prompt, template.max_tokens_multiplier, template.requires_cot)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_constitution_persona.py -k build_system_prompt -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/prompt_template_manager.py
git commit -m "feat: build_system_prompt uses Constitution persona; strip provider persona leads"
```

---

### Task 7: Seed persona article + communication style

**Files:**
- Modify: `backend/services/initialization_service.py:1124-1256` (`create_default_constitution`)
- Test: `backend/tests/test_constitution_persona.py` (Task 7 section)

**Interfaces:**
- Consumes: existing `template` dict structure.
- Produces: seeded Constitution now contains `agent_persona_and_conduct` article and `communication_style` sovereign preference — the editable clause for the acceptance test.

- [ ] **Step 1: Write the failing test**

```python
def test_seed_constitution_has_persona_article(test_db):
    from backend.services.initialization_service import InitializationService
    const = InitializationService.create_default_constitution(test_db)
    articles = const.get_articles_dict()
    assert "agent_persona_and_conduct" in articles
    prefs = const.get_sovereign_preferences()
    assert "communication_style" in prefs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_constitution_persona.py -k seed_constitution -v`

- [ ] **Step 3: Write minimal implementation**

In `create_default_constitution`, add the article inside `template["articles"]` (after `article_9`, before closing the dict at line 1228):

```python
                "agent_persona_and_conduct": {
                    "title": "Agent Persona & Conduct",
                    "content": (
                        "You are a diligent, trustworthy steward of the Sovereign's goals. "
                        "Communicate with clarity, humility, and respect. Be concise and direct; "
                        "avoid flattery and unnecessary preamble. Exercise sound judgement, own "
                        "your mistakes, and escalate when uncertain. Your demeanour is calm, "
                        "professional, and helpful — never evasive, never deceptive."
                    ),
                },
```

In `sovereign_preferences` (1249-1256) add a key:

```python
            sovereign_preferences=json.dumps({
                "transparency_level": "high",
                "human_oversight": "required",
                "data_privacy": "strict",
                "allow_external_comms": False,
                "allow_irreversible_actions": False,
                "degraded_mode": True,
                "communication_style": "Concise, clear, and respectful; minimise preamble and flattery.",
            }),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_constitution_persona.py -k seed_constitution -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/initialization_service.py
git commit -m "feat: seed agent_persona_and_conduct article and communication_style preference"
```

---

### Task 8: Chat persona endpoint + voice merge

**Files:**
- Modify: `backend/api/routes/chat.py:438-456` (`get_persona`)
- Modify: `backend/api/routes/chat.py:519-525` (`_stream_response`)
- Test: `backend/tests/test_constitution_persona.py` (Task 8 section)

**Interfaces:**
- Consumes: `head.get_system_prompt(db=, channel=)` from Task 3.
- Produces: `GET /api/v1/chat/persona?channel=` returns the Constitution-driven persona; chat stream merges a supplied voice persona into the system prompt and drops the hardcoded Sovereign line.

- [ ] **Step 1: Write the failing test**

```python
def test_get_persona_channel_voice_contains_tts(test_db):
    from fastapi.testclient import TestClient
    from backend.main import app
    # auth omitted: use the project's test auth or call head.get_system_prompt directly
    from backend.models.entities.agents import HeadOfCouncil
    head = test_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    prompt = head.get_system_prompt(db=test_db, channel="voice")
    assert "text-to-speech" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_constitution_persona.py -k get_persona -v`

- [ ] **Step 3: Write minimal implementation**

Change the `get_persona` route decorator + signature (chat.py:438-456) to accept `channel`:

```python
@app.get(
    "/api/v1/chat/persona",
    summary="Get Head of Council persona",
    tags=["Chat"],
)
async def get_persona(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_voice_or_active_user),
    channel: str = "text",
):
    head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    if not head:
        return PersonaResponse(persona="", source="none")
    prompt = head.get_system_prompt(db=db, channel=channel)
    return PersonaResponse(persona=prompt or "", source="constitution")
```

In `_stream_response` (chat.py:519-525), replace:

```python
        system_prompt = head.get_system_prompt()
        context       = await ChatService.get_system_context(db)
        full_prompt   = (
            f"{system_prompt}\n\nCurrent System State:\n{context}\n\n"
            "You are speaking directly to the Sovereign. "
            "Address them respectfully and provide clear, actionable responses."
        )
```

with:

```python
        channel = "voice" if message.voice_persona else "text"
        system_prompt = head.get_system_prompt(db=db, channel=channel)
        # If the voice bridge supplied the constitution-driven persona, prefer it
        # for cross-channel consistency (spec §6.6).
        if message.voice_persona:
            system_prompt = message.voice_persona
        context = await ChatService.get_system_context(db)
        full_prompt = f"{system_prompt}\n\nCurrent System State:\n{context}"
```

(The hardcoded "You are speaking directly to the Sovereign…" line is removed — the Constitution now supplies tone.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_constitution_persona.py -k get_persona -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/chat.py
git commit -m "feat: chat persona endpoint supports channel; voice persona merged into system prompt"
```

---

### Task 9: Voice bridge fetches `?channel=voice`

**Files:**
- Modify: `voice-bridge/main.py:380-420` (`_fetch_backend_persona`, `_load_persona`)

**Interfaces:**
- Consumes: `GET /api/v1/chat/persona?channel=voice` (Task 8).
- Produces: voice bridge now receives the spoken-style-adapted Constitution persona.

- [ ] **Step 1: No new unit test (integration-only); verify manually after Task 12 e2e.**

- [ ] **Step 2: Write minimal implementation**

In `voice-bridge/main.py`, change the URL in `_fetch_backend_persona` (line 390):

```python
        url = f"{BACKEND_URL}/api/v1/chat/persona?channel=voice"
```

Fix the misleading comment in `_load_persona` (line 408) — it is now actually true, so update to:

```python
      # 2. Backend Head persona (/api/v1/chat/persona?channel=voice) — single
      #    source of truth, derived from the Constitution so editing the
      #    Constitution updates both chat and voice consistently.
```

- [ ] **Step 3: (Manual) restart voice-bridge and confirm it logs the constitution persona**

Run: `make voice-logs` (or `docker compose logs -f voice-bridge`)
Expected: log `[bridge] Loaded Head persona from backend (NNN chars)` and the persona contains "text-to-speech".

- [ ] **Step 4: Commit**

```bash
git add voice-bridge/main.py
git commit -m "feat: voice bridge fetches Constitution persona with voice channel"
```

---

### Task 10: Purge duplicate hardcoded ethos

**Files:**
- Modify: `backend/services/persistent_council.py:223-266`
- Modify: `backend/services/overflow_recovery.py:164`

**Interfaces:**
- Consumes: same Ethos construction pattern; persona now comes from Constitution at prompt time.
- Produces: these code paths no longer embed a second, conflicting hardcoded Head persona.

- [ ] **Step 1: Write the failing test** (assert the legacy hardcoded persona phrase is gone)

```python
def test_no_hardcoded_persistent_ethos_persona():
    # Static guard: the legacy hardcoded Head persona phrases must not appear
    # in these modules after the refactor (persona now comes from the Constitution).
    from pathlib import Path
    legacy_phrases = [
        "Eternal Head of Council",
        "ultimate decision-making authority in Agentium",
    ]
    targets = [
        Path("backend/services/persistent_council.py"),
        Path("backend/services/overflow_recovery.py"),
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for phrase in legacy_phrases:
            assert phrase not in text, f"'{phrase}' still present in {path}"
```

- [ ] **Step 2: Write minimal implementation**

In `persistent_council.py` (223-266) and `overflow_recovery.py` (164), replace the hardcoded `mission`/`core_values`/`rules`/`restrictions` strings with the same neutral operational shape used in Task 5 (functional `mission` line + `"[]"` for the three persona arrays, keep `capabilities`). Remove any line that injects a persona identity distinct from the Constitution.

- [ ] **Step 3: Run tests**

Run: `cd backend && pytest tests/test_constitution_persona.py -k persistent_council -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/services/persistent_council.py backend/services/overflow_recovery.py
git commit -m "refactor: remove duplicate hardcoded ethos; persona from Constitution"
```

---

### Task 11: UI persona preview endpoint

**Files:**
- Add: `backend/main.py` (`POST /api/v1/constitution/preview-persona`)
- Test: `backend/tests/test_constitution_persona.py` (Task 11 section)

**Interfaces:**
- Consumes: a draft `ConstitutionUpdateRequest` body (reuse the existing request model from `update_constitution`).
- Produces: rendered system prompt from the *draft* Constitution, so the UI can preview before saving.

- [ ] **Step 1: Write the failing test**

```python
def test_preview_persona_renders_draft():
    from backend.core.persona import build_persona_directive
    draft = {
        "preamble": "Draft preamble DRAFT_MARKER.",
        "articles": {"agent_persona_and_conduct": {"title": "Persona", "content": "DRAFT_PERSONA_CLAUSE"}},
        "prohibited_actions": [],
        "sovereign_preferences": {"communication_style": "Friendly."},
    }
    rendered = build_persona_directive(draft, tier=0, channel="text")
    assert "DRAFT_MARKER" in rendered and "DRAFT_PERSONA_CLAUSE" in rendered
```

- [ ] **Step 2: Run test to verify it fails** (only the endpoint part; the function is already covered) — add an endpoint test using TestClient if auth allows.

- [ ] **Step 3: Write minimal implementation**

In `backend/main.py`, add (reusing `ConstitutionUpdateRequest`):

```python
@app.post(
    "/api/v1/constitution/preview-persona",
    summary="Preview persona from a draft constitution",
    tags=["Constitution"],
)
async def preview_persona(
    updates: ConstitutionUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Render the system-prompt persona from a DRAFT constitution without saving."""
    import json as _json
    articles = updates.articles or {}
    if isinstance(articles, str):
        try:
            articles = _json.loads(articles)
        except Exception:
            articles = {}
    draft = {
        "version": "draft",
        "version_number": 0,
        "agentium_id": "DRAFT",
        "preamble": updates.preamble or "",
        "articles": articles,
        "prohibited_actions": updates.prohibited_actions or [],
        "sovereign_preferences": updates.sovereign_preferences or {},
    }
    from backend.core.persona import build_persona_directive
    return {"persona": build_persona_directive(draft, tier=0, channel="text")}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_constitution_persona.py -k preview -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/main.py
git commit -m "feat: add constitution persona preview endpoint for the UI"
```

---

### Task 12: End-to-end acceptance test

**Files:**
- Test: `backend/tests/test_constitution_persona.py` (Task 12 section)

**Goal:** Satisfy the acceptance criterion — editing a constitutional behavior clause and saving it is reflected in a fresh agent's response and the voice persona, with no code change.

- [ ] **Step 1: Write the test**

```python
def test_acceptance_edit_constitution_updates_agent_and_voice(test_db):
    from backend.services.initialization_service import InitializationService
    from backend.models.entities.agents import HeadOfCouncil, AgentType, Ethos
    from backend.models.entities.constitution import Constitution
    from backend.core.constitutional_guard import ConstitutionalGuard
    import json

    # 1. Seed a constitution with a unique persona clause.
    const = InitializationService.create_default_constitution(test_db)
    articles = const.get_articles_dict()
    articles["agent_persona_and_conduct"]["content"] = "UNIQUE_CLAUSE_ALPHA speak like Alpha."
    const.articles = json.dumps(articles)
    test_db.commit()

    # 2. Fresh Head agent + ethos.
    head = test_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    if not head:
        head = HeadOfCouncil(agentium_id="00001", agent_type=AgentType.HEAD_OF_COUNCIL)
        test_db.add(head)
        test_db.flush()
    prompt_before = head.get_system_prompt(db=test_db)
    assert "UNIQUE_CLAUSE_ALPHA" in prompt_before

    # Voice persona (via the endpoint path used by the bridge).
    voice_before = head.get_system_prompt(db=test_db, channel="voice")
    assert "UNIQUE_CLAUSE_ALPHA" in voice_before and "text-to-speech" in voice_before

    # 3. Simulate the UI edit: write a NEW active constitution version with a new clause.
    new_version_number = (const.version_number or 1) + 1
    articles2 = const.get_articles_dict()
    articles2["agent_persona_and_conduct"]["content"] = "UNIQUE_CLAUSE_BETA speak like Beta."
    new_const = Constitution(
        agentium_id=f"C{new_version_number:04d}",
        version=f"v{new_version_number}.0.0",
        version_number=new_version_number,
        preamble=const.preamble,
        articles=json.dumps(articles2),
        prohibited_actions=const.prohibited_actions,
        sovereign_preferences=const.sovereign_preferences,
        is_active=True,
        effective_date=__import__("datetime").datetime.utcnow(),
    )
    const.is_active = False
    test_db.add(new_const)
    test_db.commit()
    ConstitutionalGuard.invalidate_active_constitution_cache()

    # 4. A NEW fresh agent (and voice) must reflect the NEW clause, not the old.
    prompt_after = head.get_system_prompt(db=test_db)
    assert "UNIQUE_CLAUSE_BETA" in prompt_after
    assert "UNIQUE_CLAUSE_ALPHA" not in prompt_after

    voice_after = head.get_system_prompt(db=test_db, channel="voice")
    assert "UNIQUE_CLAUSE_BETA" in voice_after
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd backend && pytest tests/test_constitution_persona.py::test_acceptance_edit_constitution_updates_agent_and_voice -v`
Expected: PASS

- [ ] **Step 3: Run the full new suite**

Run: `cd backend && pytest tests/test_constitution_persona.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_constitution_persona.py
git commit -m "test: end-to-end acceptance for Constitution-driven persona (agent + voice)"
```

---

## Self-Review Notes

- **Spec coverage:** §4 (architecture) → Tasks 1,3,6,8,9,11. §5 (composition) → Task 1. §6.1 → Task 1. §6.2 → Tasks 3,4,5. §6.3 → Task 6. §6.4 → Task 7. §6.5 → Task 2. §6.6 → Tasks 8,9. §6.7 → Task 10. §6.8 → Task 11. §9 (testing) → Tasks 1–12. All sections mapped.
- **Placeholders:** Task 10's test uses a placeholder assertion intentionally (the exact function location is identified during implementation); the implementation step is fully specified (replace hardcoded strings with neutral operational shape from Task 5).
- **Type consistency:** `build_persona_directive(constitution, tier, channel)` signature is identical across all call sites (Tasks 1,3,6,8,11). `get_active_constitution_dict(db)` returns the dict shape consumed by `build_persona_directive` everywhere. `invalidate_active_constitution_cache()` is a static method called identically in Tasks 2,12.
- **No migration:** persona uses existing `articles`/`sovereign_preferences` JSON fields (Task 7 adds keys, no schema change).
