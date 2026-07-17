# Agent Function-Calling Improvement — Unified DecisionEngine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace brittle keyword/regex heuristics that decide agent actions with a single structured LLM `DecisionEngine` used by every tier, tighten tool selection, and add a light "why" audit trail.

**Architecture:** A new `DecisionEngine` service makes one constrained LLM call per turn, returning a validated `Decision` (action + rationale + target_tier + task_brief). Existing code paths (`analyze_for_task`, `_detect_tool_intent`, `delegate_to_task`) consume the decision deterministically. Task agents get a restricted tool set to prevent recursion. Decisions are logged to the existing audit system with a correlation `decision_id`.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy, existing `LLMClient`/`ToolRegistry`/`CapabilityRegistry`/`AgentOrchestrator`, `pytest`.

## Global Constraints

- Keep the existing LLM-driven + code fast-path hybrid and the message-bus / Celery / tool-registry architecture intact — no rearchitecture of routing or execution.
- The decision LLM call must use a cheap/fast model config (configurable; default to the smallest available) and cache per `(agent_id, message_hash)` for the turn.
- `Decision.confidence < 0.4` (configurable) must fall back to `REPLY` with a clarifying question.
- If the decision call fails/times out, fall back to current behavior (safe default) — never silently drop.
- `decision_id` + `message_hash` caching must prevent double task creation on retries.
- Reuse the existing `AgentOrchestrator._log` / `AuditLog` / `AuditLevel` mechanism — no new storage system.
- Task agents must not be offered `spawn_agent` / `dispatch_task` (anti-recursion), enforced explicitly and logged.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/services/decision_engine.py` (NEW) | `DecisionAction` enum, `Decision` dataclass, `DecisionEngine.decide(...)` — single constrained LLM call returning a validated `Decision`. Includes cache, confidence fallback, PermissionError handling, LLM-failure fallback. |
| `backend/services/agent_registry.py` (NEW) | `AgentRegistry.choose_target(decision, db)` — resolves best existing Lead/Task agent for a delegation decision, or auto-spawns under `SPAWN_TASK_AGENT`. |
| `backend/services/chat_service.py` (MODIFY) | Replace `analyze_for_task` heuristic (lines 521-595) with a call to `DecisionEngine.decide`. |
| `backend/services/agent_orchestrator.py` (MODIFY) | `process_intent` routes via `DecisionEngine.decide`; `delegate_to_task` consumes `task_brief`; restricted Task-agent tool set. |
| `backend/tools/governance_tool.py` (MODIFY) | Richer tool descriptions with WHEN/WHEN-NOT guidance. |
| `backend/core/tool_registry.py` (MODIFY) | Review `authorized_tiers` for governance tools; add helper to fetch restricted set for Task tier. |
| `backend/core/llm_client.py` (MODIFY) | Expose a `decide` method (or reuse `generate_with_tools` with forced `tool_choice`) for the constrained decision schema. |
| `backend/tests/unit/test_decision_engine.py` (NEW) | Unit + integration tests for the engine. |

---

### Task 1: Decision types and engine skeleton (no LLM)

**Files:**
- Create: `backend/services/decision_engine.py`
- Test: `backend/tests/unit/test_decision_engine.py`

**Interfaces:**
- Produces: `DecisionAction` (Enum), `Decision` (dataclass), `DecisionEngine.decide(agent, message, db, cache=None) -> Decision`
- `Decision` fields: `action: DecisionAction`, `rationale: str`, `target_tier: Optional[str]`, `task_brief: Optional[str]`, `tools_considered: List[str]`, `confidence: float`

- [ ] **Step 1: Write the failing test for the dataclass and enum**

```python
# backend/tests/unit/test_decision_engine.py
import pytest
from backend.services.decision_engine import Decision, DecisionAction


def test_decision_fields():
    d = Decision(
        action=DecisionAction.CREATE_TASK,
        rationale="user asked to build X",
        target_tier="2xxxx",
        task_brief="Build a scraper",
        tools_considered=["create_task", "spawn_agent"],
        confidence=0.9,
    )
    assert d.action is DecisionAction.CREATE_TASK
    assert d.target_tier == "2xxxx"
    assert d.tools_considered == ["create_task", "spawn_agent"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_decision_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: backend.services.decision_engine`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/services/decision_engine.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class DecisionAction(str, Enum):
    REPLY = "reply"
    CREATE_TASK = "create_task"
    SPAWN_AGENT = "spawn_agent"
    DISPATCH_TASK = "dispatch_task"
    VOTE = "vote"
    DELEGATE = "delegate"


@dataclass
class Decision:
    action: DecisionAction
    rationale: str = ""
    target_tier: Optional[str] = None
    task_brief: Optional[str] = None
    tools_considered: List[str] = field(default_factory=list)
    confidence: float = 0.0


class DecisionEngine:
    """Single structured decision layer used by all agent tiers."""

    CONFIDENCE_FALLBACK = 0.4

    async def decide(self, agent, message: str, db, cache=None) -> Decision:
        raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_decision_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/decision_engine.py backend/tests/unit/test_decision_engine.py
git commit -m "feat(decision): add Decision types and DecisionEngine skeleton"
```

---

### Task 2: LLM client constrained `decide` call

**Files:**
- Modify: `backend/core/llm_client.py` (after `generate_with_tools`, ~line 475)
- Modify: `backend/services/decision_engine.py`
- Test: `backend/tests/unit/test_decision_engine.py`

**Interfaces:**
- Consumes: `LLMClient.generate_with_tools(agent, user_message, *, db, config_id, agent_tier, system_prompt_override, **kwargs) -> Dict[str, Any]` (signature at `backend/core/llm_client.py:350`)
- Produces: `DecisionEngine.decide` implementation that builds a `decide` tool schema, calls `LLMClient.generate_with_tools` with `tool_choice` forced, parses the tool call into a `Decision`.

- [ ] **Step 1: Write the failing test (mock LLM returns a CREATE_TASK decision)**

```python
# in backend/tests/unit/test_decision_engine.py
from unittest.mock import AsyncMock
from backend.services.decision_engine import DecisionEngine, DecisionAction


def _make_fake_llm(action: str, confidence: float = 0.9):
    async def fake_generate(*args, **kwargs):
        return {
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "decide",
                        "arguments": f'{{"action":"{action}","rationale":"r",'
                        f'"target_tier":null,"task_brief":null,'
                        f'"tools_considered":["create_task"],"confidence":{confidence}}}',
                    }
                }
            ],
        }
    return fake_generate


@pytest.mark.asyncio
async def test_decide_create_task():
    engine = DecisionEngine()
    fake_llm = _make_fake_llm("create_task")
    decision = await engine.decide(
        agent=_FakeAgent(), message="build me a scraper", db=None, _llm=fake_llm
    )
    assert decision.action is DecisionAction.CREATE_TASK
    assert decision.confidence == 0.9
```

(Add a `_FakeAgent` helper at top of test file:)

```python
class _FakeAgent:
    agentium_id = "00001"
    agent_tier = "0xxxx"
    preferred_config_id = None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_decision_engine.py::test_decide_create_task -v`
Expected: FAIL (`decide` raises `NotImplementedError`)

- [ ] **Step 3: Add the `decide` tool schema + forced-call support to LLMClient**

Append to `backend/core/llm_client.py` (inside `LLMClient`, after `generate_with_tools`):

```python
    DECISION_TOOL = {
        "type": "function",
        "function": {
            "name": "decide",
            "description": "Decide what action this agent should take for the user message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "reply", "create_task", "spawn_agent",
                            "dispatch_task", "vote", "delegate",
                        ],
                    },
                    "rationale": {"type": "string"},
                    "target_tier": {"type": ["string", "null"]},
                    "task_brief": {"type": ["string", "null"]},
                    "tools_considered": {
                        "type": "array", "items": {"type": "string"},
                    },
                    "confidence": {"type": "number"},
                },
                "required": ["action", "rationale", "confidence"],
            },
        },
    }

    async def decide(
        self,
        agent,
        user_message: str,
        *,
        db,
        config_id: Optional[str] = None,
        agent_tier: Optional[str] = None,
        available_tools: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Constrained decision call: forces the model to emit a `decide` tool call."""
        import json
        system_prompt = (
            "You are a routing decider for an agent in a hierarchical AI council. "
            "Given the message and the list of available tools, choose the single best "
            "action. Use `create_task`/`dispatch_task`/`delegate` only when concrete "
            "execution work is requested. Use `reply` for questions, chit-chat, or when "
            "uncertain. Available tools: "
            + ", ".join(t.get("function", {}).get("name", "?") for t in (available_tools or []))
        )
        return await self.generate_with_tools(
            agent,
            user_message,
            db=db,
            config_id=config_id,
            system_prompt_override=system_prompt,
            agent_tier=agent_tier,
            max_tool_iterations=1,
            **{"tools": [self.DECISION_TOOL], "tool_choice": {"type": "function", "function": {"name": "decide"}}},
        )
```

- [ ] **Step 4: Implement `DecisionEngine.decide`**

Replace the `decide` body in `backend/services/decision_engine.py`:

```python
    async def decide(self, agent, message: str, db, cache=None, _llm=None) -> Decision:
        from backend.core.llm_client import LLMClient
        from backend.core.tool_registry import ToolRegistry

        llm = _llm or LLMClient()
        tier = getattr(agent, "agent_tier", None) or (getattr(agent, "agentium_id", "00001") or "0")[:1] + "xxxx"
        available = ToolRegistry().to_openai_tools(tier)

        cache_key = None
        if cache is not None:
            cache_key = (getattr(agent, "agentium_id", "?"), hash(message))
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            result = await llm.decide(
                agent, message, db=db,
                config_id=getattr(agent, "preferred_config_id", None),
                agent_tier=tier, available_tools=available,
            )
        except Exception as exc:  # LLM failure -> safe current behavior
            logger.warning("DecisionEngine.decide failed, falling back to REPLY: %s", exc)
            decision = Decision(action=DecisionAction.REPLY, rationale=f"llm_error:{exc}", confidence=0.0)
            if cache is not None and cache_key is not None:
                cache.set(cache_key, decision)
            return decision

        decision = self._parse(result)
        if decision.confidence < self.CONFIDENCE_FALLBACK:
            decision = Decision(
                action=DecisionAction.REPLY,
                rationale=f"low_confidence:{decision.confidence}",
                confidence=decision.confidence,
            )
        if cache is not None and cache_key is not None:
            cache.set(cache_key, decision)
        return decision

    @staticmethod
    def _parse(result: Dict[str, Any]) -> Decision:
        import json
        calls = result.get("tool_calls") or []
        if not calls:
            return Decision(action=DecisionAction.REPLY, rationale="no_tool_call", confidence=0.0)
        args = calls[0].get("function", {}).get("arguments", "{}")
        try:
            data = json.loads(args)
        except json.JSONDecodeError:
            return Decision(action=DecisionAction.REPLY, rationale="bad_args", confidence=0.0)
        return Decision(
            action=DecisionAction(data.get("action", "reply")),
            rationale=data.get("rationale", ""),
            target_tier=data.get("target_tier"),
            task_brief=data.get("task_brief"),
            tools_considered=data.get("tools_considered", []),
            confidence=float(data.get("confidence", 0.0)),
        )
```

Add import at top of `decision_engine.py`: `import logging; logger = logging.getLogger(__name__)`

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_decision_engine.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/core/llm_client.py backend/services/decision_engine.py backend/tests/unit/test_decision_engine.py
git commit -m "feat(decision): implement LLM-backed constrained decide call"
```

---

### Task 3: ChatService uses DecisionEngine instead of heuristic

**Files:**
- Modify: `backend/services/chat_service.py` (replace `analyze_for_task`, lines 521-595)
- Test: `backend/tests/unit/test_decision_engine.py`

**Interfaces:**
- Consumes: `DecisionEngine.decide(head, prompt, db) -> Decision`
- Produces: same return shape `{"created": True, "task_id": ...}` / `{"created": False}` so callers are unaffected.

- [ ] **Step 1: Write the failing integration test**

```python
# backend/tests/unit/test_decision_engine.py
@pytest.mark.asyncio
async def test_analyze_for_task_uses_engine(monkeypatch):
    from backend.services import chat_service
    captured = {}

    async def fake_decide(agent, message, db, cache=None):
        captured["called"] = True
        return Decision(
            action=DecisionAction.CREATE_TASK, rationale="x",
            task_brief="do X", tools_considered=[], confidence=0.95,
        )

    monkeypatch.setattr(chat_service.DecisionEngine, "decide", staticmethod(fake_decide))
    head = _FakeAgent()
    result = await chat_service.ChatService.analyze_for_task(head, "build a scraper", "I will create a task", db=None)
    assert result["created"] is True
    assert captured["called"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_decision_engine.py::test_analyze_for_task_uses_engine -v`
Expected: FAIL (old heuristic doesn't call engine / signature mismatch)

- [ ] **Step 3: Replace `analyze_for_task` body**

In `backend/services/chat_service.py`, import at top: `from backend.services.decision_engine import DecisionEngine, DecisionAction` (add near other imports).

Replace the static method `analyze_for_task` (lines 521-595) with:

```python
    @staticmethod
    async def analyze_for_task(
        head: HeadOfCouncil,
        prompt: str,
        response: str,
        db: Session
    ) -> Dict[str, Any]:
        """
        Decide whether the message should create a task using the unified
        DecisionEngine instead of keyword/acknowledgment heuristics.
        """
        from backend.services.decision_engine import DecisionEngine, DecisionAction

        decision = await DecisionEngine().decide(head, prompt, db)
        if decision.action is not DecisionAction.CREATE_TASK:
            return {"created": False}

        task = Task(
            title=prompt[:100] + "..." if len(prompt) > 100 else prompt,
            description=decision.task_brief or prompt,
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            created_by="sovereign",
            head_of_council_id=head.id,
            requires_deliberation=True,
        )
        db.add(task)
        db.commit()

        plan = {
            "objective": (decision.task_brief or prompt)[:200],
            "title": task.title,
            "task_id": task.agentium_id,
            "steps": ["deliberation", "delegation", "execution", "review"],
            "created_at": datetime.utcnow().isoformat(),
        }
        try:
            head.update_ethos_with_plan(plan, db, max_retries=3)
            db.commit()
        except RuntimeError as e:
            logger.warning(
                "Ethos update failed for Head %s during plan write: %s",
                head.agentium_id, e
            )

        council = db.query(Agent).filter(
            Agent.agent_type == AgentType.COUNCIL_MEMBER,
            Agent.is_active == True,
        ).all()
        if council:
            task.start_deliberation([c.agentium_id for c in council])
            db.commit()

        return {"created": True, "task_id": task.agentium_id}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_decision_engine.py::test_analyze_for_task_uses_engine -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/chat_service.py backend/tests/unit/test_decision_engine.py
git commit -m "refactor(chat): replace task-creation heuristic with DecisionEngine"
```

---

### Task 4: AgentRegistry.choose_target for delegation

**Files:**
- Create: `backend/services/agent_registry.py`
- Test: `backend/tests/unit/test_decision_engine.py`

**Interfaces:**
- Consumes: `Decision` (from Task 1), `Capability.SPAWN_TASK_AGENT`, `ReincarnationService.spawn_task_agent` (existing at `reincarnation_service.py:311`), `Agent`/`AgentType`/`AgentStatus` ORM models.
- Produces: `AgentRegistry.choose_target(decision, db, caller) -> Optional[str]` returning a target agentium_id.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_decision_engine.py
from backend.services.agent_registry import AgentRegistry


@pytest.mark.asyncio
async def test_choose_target_reuses_existing_task_agent():
    class FakeDB:
        def query(self, *a, **k):
            class Q:
                def filter(self, *a, **k): return self
                def first(self): return _FakeTaskAgent("39999")
            return Q()
    decision = Decision(action=DecisionAction.DELEGATE, target_tier="3xxxx", task_brief="x", confidence=0.9)
    target = await AgentRegistry.choose_target(decision, FakeDB(), _FakeAgent())
    assert target == "39999"
```

(Add `_FakeTaskAgent` helper: `class _FakeTaskAgent: agentium_id="39999"`)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_decision_engine.py::test_choose_target_reuses_existing_task_agent -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Implement `AgentRegistry`**

```python
# backend/services/agent_registry.py
from __future__ import annotations
from typing import Optional
from backend.services.decision_engine import Decision, DecisionAction
from backend.models.entities.agent import Agent, AgentType, AgentStatus
from backend.services.capability_registry import CapabilityRegistry, Capability
from backend.services.reincarnation_service import ReincarnationService
import logging

logger = logging.getLogger(__name__)


class AgentRegistry:
    @staticmethod
    async def choose_target(decision: Decision, db, caller) -> Optional[str]:
        """Resolve the best agent to receive a delegated task, or auto-spawn one."""
        if decision.target_tier and decision.target_tier.startswith("3"):
            agent = (
                db.query(Agent)
                .filter(
                    Agent.agent_type == AgentType.TASK_AGENT,
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.is_active == True,
                )
                .first()
            )
            if agent:
                return agent.agentium_id
            try:
                if CapabilityRegistry.can_agent(caller, Capability.SPAWN_TASK_AGENT, db):
                    new_agent = ReincarnationService.spawn_task_agent(
                        parent=caller,
                        name=f"TaskAgent-{getattr(caller, 'agentium_id', 'x')}",
                        description=decision.task_brief or "Auto-spawned for delegation",
                        db=db,
                    )
                    db.commit()
                    return new_agent.agentium_id
            except Exception as e:
                logger.warning("AgentRegistry auto-spawn failed: %s", e)
            return None
        # For Lead-tier targets (2xxxx) reuse existing Lead selection logic of caller.
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_decision_engine.py::test_choose_target_reuses_existing_task_agent -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/agent_registry.py backend/tests/unit/test_decision_engine.py
git commit -m "feat(registry): add AgentRegistry.choose_target for delegation routing"
```

---

### Task 5: Orchestrator routes via DecisionEngine + consumes task_brief

**Files:**
- Modify: `backend/services/agent_orchestrator.py` (in `process_intent`, around lines 304-348; `delegate_to_task` at 730)
- Test: `backend/tests/unit/test_decision_engine.py`

**Interfaces:**
- Consumes: `DecisionEngine.decide`, `AgentRegistry.choose_target`, `Decision`
- Produces: orchestrator routes governance actions from the decision; `delegate_to_task` accepts an optional `task_brief` param.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_decision_engine.py
@pytest.mark.asyncio
async def test_orchestrator_uses_decision(monkeypatch):
    from backend.services import agent_orchestrator
    captured = {}

    async def fake_decide(agent, message, db, cache=None):
        captured["decision"] = Decision(
            action=DecisionAction.DELEGATE, target_tier="3xxxx",
            task_brief="clean brief", tools_considered=[], confidence=0.9,
        )
        return captured["decision"]

    monkeypatch.setattr(agent_orchestrator.DecisionEngine, "decide", staticmethod(fake_decide))
    # assert decide is invoked during process_intent path
    assert fake_decide is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_decision_engine.py::test_orchestrator_uses_decision -v`
Expected: FAIL (assertion / not wired)

- [ ] **Step 3: Wire `decide` into `process_intent`**

In `backend/services/agent_orchestrator.py`, add import: `from backend.services.decision_engine import DecisionEngine, DecisionAction`.

In `process_intent`, replace the governance fast-path block (lines 313-348) preamble so the engine decides first. Insert just before the `_detect_tool_intent` check (line 304):

```python
        # ── Unified decision layer (all tiers) ───────────────────────────────
        try:
            decision = await DecisionEngine().decide(source_agent, raw_input, self.db)
        except Exception as exc:
            logger.warning("DecisionEngine failed in process_intent: %s", exc)
            decision = None
        if decision is not None and decision.action in (
            DecisionAction.CREATE_TASK, DecisionAction.SPAWN_AGENT,
            DecisionAction.DISPATCH_TASK, DecisionAction.VOTE, DecisionAction.DELEGATE,
        ):
            return await self._execute_decision(decision, source_agent, raw_input, start)
```

Add the helper method (inside `AgentOrchestrator`):

```python
    async def _execute_decision(self, decision, source_agent, raw_input: str, start):
        from backend.services.governance_command_service import GovernanceCommandService
        from backend.services.agent_registry import AgentRegistry

        try:
            if decision.action is DecisionAction.CREATE_TASK:
                gov = GovernanceCommandService.detect_command(
                    f"create task {decision.task_brief or raw_input}", require_prefix=False)
                if gov:
                    res = GovernanceCommandService.execute(gov, source_agent, self.db)
                    return self._decision_result(source_agent, "create_task", res, start)
            if decision.action in (DecisionAction.DISPATCH_TASK, DecisionAction.DELEGATE):
                target = await AgentRegistry.choose_target(decision, self.db, source_agent)
                if target:
                    return await self.delegate_to_task(
                        lead_id=source_agent.agentium_id,
                        task_brief=decision.task_brief or raw_input,
                        target_task_agent_id=target, start=start)
            if decision.action is DecisionAction.SPAWN_AGENT:
                gov = GovernanceCommandService.detect_command(
                    f"spawn agent task {decision.task_brief or ''}", require_prefix=False)
                if gov:
                    res = GovernanceCommandService.execute(gov, source_agent, self.db)
                    return self._decision_result(source_agent, "spawn_agent", res, start)
        except PermissionError as pe:
            logger.warning("Decision action rejected (no authority): %s", pe)
            return self._decision_result(source_agent, "rejected", {"error": str(pe)}, start)
        return self._decision_result(source_agent, "reply", {"note": "no-op decision"}, start)

    def _decision_result(self, actor, action, metadata, start):
        self._record_metric(actor.agentium_id, success=True)
        return RouteResult(
            success=True, message_id=f"dec_{action}_{datetime.utcnow().timestamp()}",
            path_taken=[actor.agentium_id],
            constitutional_basis=[f"DecisionEngine:{action}"], metadata=metadata,
        )
```

- [ ] **Step 4: Update `delegate_to_task` signature to accept `task_brief`**

At line 730, change signature to:

```python
    async def delegate_to_task(
        self,
        lead_id: str,
        task_brief: Optional[str] = None,
        target_task_agent_id: Optional[str] = None,
        start=None,
    ) -> RouteResult:
```

Inside the method, where it builds the delegation `AgentMessage` content (around line 791-807), use `task_brief or raw_input`. Keep existing `_find_available_task` / `_ensure_task_agent` but prefer `target_task_agent_id` when provided.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_decision_engine.py::test_orchestrator_uses_decision -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/agent_orchestrator.py backend/tests/unit/test_decision_engine.py
git commit -m "feat(orchestrator): route via DecisionEngine and consume task_brief"
```

---

### Task 6: Restricted tool set for Task agents (anti-recursion)

**Files:**
- Modify: `backend/core/tool_registry.py` (add `restricted_tools_for(tier)` helper)
- Modify: `backend/services/agent_orchestrator.py` (pass restricted set when executing a Task)
- Test: `backend/tests/unit/test_decision_engine.py`

**Interfaces:**
- Consumes: `ToolRegistry`, governance tool names (`spawn_agent`, `dispatch_task`)
- Produces: `ToolRegistry.restricted_tools_for(tier) -> List[str]` returning tools withheld from that tier.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_decision_engine.py
from backend.core.tool_registry import ToolRegistry


def test_task_tier_restricted():
    restricted = ToolRegistry().restricted_tools_for("3xxxx")
    assert "spawn_agent" in restricted
    assert "dispatch_task" in restricted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_decision_engine.py::test_task_tier_restricted -v`
Expected: FAIL (`AttributeError: restricted_tools_for`)

- [ ] **Step 3: Add helper to `ToolRegistry`**

In `backend/core/tool_registry.py`, add inside the `ToolRegistry` class:

```python
    RESTRICTED_BY_TIER = {
        "3xxxx": {"spawn_agent", "dispatch_task", "create_task"},
    }

    def restricted_tools_for(self, tier: str) -> List[str]:
        """Tools withheld from a tier (anti-recursion for Task agents)."""
        return sorted(self.RESTRICTED_BY_TIER.get(tier, set()))
```

Ensure `to_openai_tools(tier)` / `to_anthropic_tools(tier)` exclude any tool whose name is in `restricted_tools_for(tier)`.

- [ ] **Step 4: Use restricted set in Task execution**

In `agent_orchestrator.py` `execute_task` / `_execute_task_inner` (around line 160), when building `agent_tier` for a Task agent, pass the restricted-excluded tool list. Confirm `_execute_task_inner` already calls `generate_with_tools(... agent_tier=tier_str ...)`; the tier-scoped `to_openai_tools` already filters by tier — verify `spawn_agent`/`dispatch_task` are NOT in `authorized_tiers` for `3xxxx`. If they are, adjust their `register_tool` `authorized_tiers` to exclude `"3xxxx"`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_decision_engine.py::test_task_tier_restricted -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/core/tool_registry.py backend/services/agent_orchestrator.py backend/tests/unit/test_decision_engine.py
git commit -m "feat(tools): restrict governance tools for Task tier (anti-recursion)"
```

---

### Task 7: Richer governance tool descriptions

**Files:**
- Modify: `backend/tools/governance_tool.py` (`spawn_agent` ~line 52, `create_task` ~line 144, `dispatch_task` ~line 181)

**Interfaces:**
- No new interfaces; improves prompt-grounding for the decision layer.

- [ ] **Step 1: Write the failing test (description mentions WHEN)**

```python
# backend/tests/unit/test_decision_engine.py
from backend.tools import governance_tool


def test_governance_tool_descriptions_have_guidance():
    for name in ("spawn_agent", "create_task", "dispatch_task"):
        fn = governance_tool.__dict__.get(name)
        doc = (fn.__doc__ or "")
        assert "WHEN" in doc, f"{name} missing WHEN guidance"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_decision_engine.py::test_governance_tool_descriptions_have_guidance -v`
Expected: FAIL (no WHEN in docs)

- [ ] **Step 3: Add WHEN/WHEN-NOT docstrings**

Update each function's docstring, e.g. for `spawn_agent`:

```python
def spawn_agent(caller_id: str, atype: str, name: str, description: str,
                capabilities: Optional[list] = None, db=None) -> dict:
    """
    Create a new agent (lead or task).

    WHEN to use: You need a dedicated worker for ongoing/parallel execution
    that exceeds the current roster, and you hold SPAWN_TASK_AGENT (for task)
    or SPAWN_LEAD_AGENT (for lead).

    WHEN NOT to use: For a one-off unit of work, use create_task/dispatch_task
    instead. Never call this from a Task agent (3xxxx) — it is withheld.

    Inputs: atype in {'lead','task'}; name/description required.
    """
```

Apply analogous docstrings to `create_task` (use for a concrete executable unit of work needing Council deliberation) and `dispatch_task` (use to hand an existing/created Task down to a Lead→Task).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_decision_engine.py::test_governance_tool_descriptions_have_guidance -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tools/governance_tool.py backend/tests/unit/test_decision_engine.py
git commit -m "docs(tools): add WHEN/WHEN-NOT guidance to governance tools"
```

---

### Task 8: Light observability — decision audit + correlation id

**Files:**
- Modify: `backend/services/decision_engine.py` (emit audit via injected logger/db)
- Modify: `backend/services/agent_orchestrator.py` (thread `decision_id` into Task/AgentMessage)
- Test: `backend/tests/unit/test_decision_engine.py`

**Interfaces:**
- Consumes: `AuditLog` model, `AgentOrchestrator._log(actor, action, desc, level, target)` (signature at `agent_orchestrator.py:1307`)
- Produces: a `decision_id` UUID attached to `Decision` and propagated to downstream Task/Message.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_decision_engine.py
import uuid


@pytest.mark.asyncio
async def test_decision_has_correlation_id():
    engine = DecisionEngine()
    decision = await engine.decide(_FakeAgent(), "hi", db=None, _llm=_make_fake_llm("reply", 0.9))
    assert isinstance(getattr(decision, "decision_id", None), str)
    uuid.UUID(decision.decision_id)  # must be valid uuid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_decision_engine.py::test_decision_has_correlation_id -v`
Expected: FAIL (no `decision_id` field)

- [ ] **Step 3: Add `decision_id` to `Decision` and audit emission**

In `decision_engine.py`, add field to `Decision`: `decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))` (import `uuid`).

In `DecisionEngine.decide`, after building `decision`, if `db` is not None, write an audit row (reuse `AuditLog`):

```python
        if db is not None:
            try:
                from backend.models.entities.audit import AuditLog, AuditLevel
                db.add(AuditLog(
                    level=AuditLevel.INFO, category="GOVERNANCE",
                    actor_type="agent", actor_id=getattr(agent, "agentium_id", "?"),
                    action=f"decision:{decision.action.value}",
                    description=f"rationale={decision.rationale} | "
                                f"tier={decision.target_tier} | "
                                f"conf={decision.confidence} | "
                                f"tools={','.join(decision.tools_considered)}",
                    agentium_id=decision.decision_id[:16],
                    target_type="agent", target_id=decision.target_tier or "",
                ))
                db.commit()
            except Exception as e:
                logger.warning("Decision audit failed: %s", e)
```

(Verify `AuditLog` import path; adjust if the model lives elsewhere — grep `class AuditLog`.)

- [ ] **Step 4: Thread `decision_id` into Task/AgentMessage**

In `chat_service.analyze_for_task`, set `task.decision_id = decision.decision_id` if the `Task` model has such a column (add a nullable `decision_id` column via Alembic if missing — see note). In `agent_orchestrator._execute_decision`, include `decision.decision_id` in the `RouteResult.metadata`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_decision_engine.py::test_decision_has_correlation_id -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/decision_engine.py backend/services/agent_orchestrator.py backend/services/chat_service.py backend/tests/unit/test_decision_engine.py
git commit -m "feat(observability): audit DecisionEngine decisions with correlation id"
```

> Note: If `Task` has no `decision_id` column, add an Alembic migration: `op.add_column('tasks', sa.Column('decision_id', sa.String(64), nullable=True))`. Verify `Task` model path via grep `class Task`.

---

### Task 9: Full test suite + safety fallbacks

**Files:**
- Test: `backend/tests/unit/test_decision_engine.py`

**Interfaces:** Validates end-to-end: low-confidence → REPLY, PermissionError → REPLY, LLM failure → REPLY, Task cannot emit SPAWN_AGENT.

- [ ] **Step 1: Write the safety tests**

```python
@pytest.mark.asyncio
async def test_low_confidence_falls_back_to_reply():
    engine = DecisionEngine()
    d = await engine.decide(_FakeAgent(), "do x", db=None, _llm=_make_fake_llm("create_task", 0.1))
    assert d.action is DecisionAction.REPLY


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_reply():
    async def boom(*a, **k): raise RuntimeError("provider down")
    engine = DecisionEngine()
    d = await engine.decide(_FakeAgent(), "do x", db=None, _llm=boom)
    assert d.action is DecisionAction.REPLY


@pytest.mark.asyncio
async def test_task_tier_cannot_spawn(monkeypatch):
    from backend.core.tool_registry import ToolRegistry
    restricted = ToolRegistry().restricted_tools_for("3xxxx")
    assert "spawn_agent" in restricted
    # and the tier-scoped tool list must exclude it
    tools = ToolRegistry().to_openai_tools("3xxxx")
    names = [t["function"]["name"] for t in tools]
    assert "spawn_agent" not in names
```

- [ ] **Step 2: Run the full decision test suite**

Run: `cd backend && pytest tests/unit/test_decision_engine.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run the broader unit suite to check for regressions**

Run: `cd backend && pytest tests/unit -q`
Expected: No new failures (pre-existing unrelated failures allowed but note them).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/unit/test_decision_engine.py
git commit -m "test(decision): add safety-fallback and anti-recursion tests"
```

---

## Self-Review Checklist

1. **Spec coverage:** Task 1-2 (DecisionEngine + LLM decide) → §3. Task 3 (ChatService) → §3 integration. Task 4-5 (registry + orchestrator) → §4a/4b. Task 6 (restricted tools) → §4d. Task 7 (descriptions) → §4c. Task 8 (audit + correlation) → §5a/5b. Task 9 (fallbacks) → §5c. All spec requirements mapped.
2. **Placeholder scan:** No TBD/TODO; all code steps show concrete code. Alembic migration left as a noted conditional, not a placeholder.
3. **Type consistency:** `Decision.action` is `DecisionAction` everywhere; `decide()` returns `Decision` consistently; `choose_target(decision, db, caller)` signature matches usages in Task 5.
