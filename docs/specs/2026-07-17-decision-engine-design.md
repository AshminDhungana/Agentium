# Agent Function-Calling Improvement — Unified DecisionEngine

**Date:** 2026-07-17
**Status:** Approved (design)
**Scope:** Improvement to the agent action/function pipeline across all tiers (Head intake, Council routing, Lead→Task delegation, Task execution).

## 1. Problem

Today, an agent's decision to act is driven by brittle heuristics rather than a single coherent mechanism:

- `ChatService.analyze_for_task` (`backend/services/chat_service.py:521`) decides whether to create a Task using a **keyword + acknowledgment heuristic** — it only fires if the user said a word like "create" AND the Head's reply contained phrases like "I will". This misses real tasks and creates phantom ones.
- `AgentOrchestrator._detect_tool_intent` (`backend/services/agent_orchestrator.py:397`) uses **regex** to guess tool commands, which is fragile and easily mis-triggered by prose.
- Tool/agent selection during delegation relies on the LLM picking from tier-scoped tool lists with often-vague descriptions, leading to mismatches.
- There is little recorded "why" behind an agent's action, making the system hard to debug after the fact.

Goal: replace the brittle heuristics with a single structured LLM decision layer used by every tier, tighten tool selection, and add a light "why" audit trail — without changing the underlying message-bus / Celery / tool-registry architecture.

## 2. Approach

**Approach A — Unified `DecisionEngine` (chosen).** Every tier first calls one LLM "decision" step that returns a typed, validated `Decision`. Code then acts on that decision deterministically. This keeps the LLM as the brain, fits the existing architecture, and fixes all three pains (brittle heuristics, tool/agent mismatch, no observability) with low risk.

Rejected alternatives:
- **B — Handoffs / agents-as-tools:** idiomatic but requires large rearchitecture of `message_bus`/`process_intent`; high risk to a working system.
- **C — Pure code/rules orchestration:** most predictable but loses the flexible delegation the system is built around.

## 3. Section 1 — The `DecisionEngine` and `Decision` type

**New module:** `backend/services/decision_engine.py`

```python
class DecisionAction(str, Enum):
    REPLY         # respond directly, no task
    CREATE_TASK   # open a Task + Council deliberation
    SPAWN_AGENT   # create a new Lead/Task agent
    DISPATCH_TASK # delegate an existing/created Task down to a Lead
    VOTE          # raise a Council vote / amendment
    DELEGATE      # hand work to a child agent (Lead->Task)

@dataclass
class Decision:
    action: DecisionAction
    rationale: str                 # "why" — written to audit log
    target_tier: Optional[str]     # e.g. "2xxxx" for delegation target
    task_brief: Optional[str]      # structured brief for Create/Dispatch/Delegate
    tools_considered: List[str]    # for observability
    confidence: float
```

`DecisionEngine.decide(agent, message, db)` makes **one** LLM call with a constrained schema (function-calling with `tool_choice` forced to the `decide` function). It is given the agent's tier-filtered tool list as context so the model grounds its choice in what is actually available. Returns a validated `Decision`.

**Integration points (replacing old code):**
- `chat_service.py` `analyze_for_task` → replaced by `DecisionEngine.decide(head, ...)`. `action == CREATE_TASK` drives the existing `Task(...)` + `start_deliberation` block.
- `agent_orchestrator.py` `_detect_tool_intent` / governance fast-path → the orchestrator first calls `decide()`; if `action` is a governance action it routes to the existing `ToolCreationService` / governance tools deterministically.

**Cost guard:** The decision call uses a cheap/fast model config (configurable, default smallest available) and results are cached per `(agent_id, message_hash)` for the turn.

## 4. Section 2 — Delegation quality and tool/agent selection

**2a. Decision carries routing intent.** When `Decision.action` is `DISPATCH_TASK` / `DELEGATE`, the LLM emits `target_tier` and a structured `task_brief` (objective, acceptance criteria, constraints). `AgentOrchestrator.delegate_to_task` consumes the brief instead of the raw user string.

**2b. Agent/tier matching.** Add `AgentRegistry.choose_target(decision, db)` in a new `backend/services/agent_registry.py` that, given `target_tier` + capability needs from `task_brief`, resolves the best existing Lead/Task agent (reusing `_find_available_task` / `_ensure_task_agent` logic from `agent_orchestrator.py:1232`). If none exists and the caller holds `SPAWN_TASK_AGENT`, it auto-spawns — triggered by the decision, not a hard-coded heuristic.

**2c. Tool-selection accuracy (fewer mismatches), no architecture change:**
- Richer tool descriptions for governance tools (`spawn_agent`, `create_task`, `dispatch_task` in `tools/governance_tool.py`) with explicit "WHEN to use / WHEN NOT to use" and input-shape guidance.
- Tier-scoping review of `ToolRegistry.register_tool` `authorized_tiers` so e.g. `dispatch_task` is not offered to tiers that cannot act on it.
- Pre-decision tool grounding: the decision call already receives the tier-filtered tool list.

**2d. Anti-recursion.** Task agents get a *restricted* tool set without `spawn_agent` / `dispatch_task` so a Task cannot spawn its own sub-org. Mirrors the sub-agent delegation pattern (restricted tool set prevents infinite recursion). Already partly enforced by tier scoping; make it explicit and logged.

## 5. Section 3 — Observability (light) and error handling

**5a. Decision audit (reuses existing audit log).** Extend the existing `_log` / audit mechanism (`AgentOrchestrator._log`, `AuditLevel`) with a `decision` action recording: `actor`, `action`, `rationale`, `target_tier`, `task_brief` (truncated), `tools_considered`, `confidence`, `model_used`. One row per decision turn. No new storage system.

**5b. Correlation.** Add a `decision_id` (UUID) threaded through: `Decision` → `Task` / `AgentMessage` → execution, so a decision can be traced to the work it spawned. Reuses the existing `message_id` linkage where possible.

**5c. Error handling / safety.**
- **Low confidence:** if `Decision.confidence < threshold` (configurable, default 0.4), fall back to `REPLY` with a clarifying question instead of guessing — prevents phantom tasks.
- **Invalid action for tier:** if the LLM emits an action the agent is not authorized for, `CapabilityRegistry.can_agent` blocks it; the engine catches `PermissionError` and downgrades to `REPLY` with a reason in the audit log.
- **LLM failure / timeout:** if the decision call fails, fall back to the current behavior (safe default) so the system degrades gracefully, not silently.
- **Idempotency:** `decision_id` + `message_hash` cache prevents double task creation on retries.

**5d. Testing.**
- Unit tests for `DecisionEngine.decide` with mocked LLM returning each action.
- Integration test: a "create a task to X" message yields one `CREATE_TASK` decision + one `Task` row.
- Test that a Task agent cannot emit `SPAWN_AGENT`.

## 6. Files touched (summary)

| File | Change |
|---|---|
| `backend/services/decision_engine.py` | NEW — `DecisionEngine`, `Decision`, `DecisionAction` |
| `backend/services/chat_service.py` | Replace `analyze_for_task` heuristic with `DecisionEngine.decide` |
| `backend/services/agent_orchestrator.py` | Route via `decide()`; consume `task_brief` in `delegate_to_task` |
| `backend/services/agent_registry.py` | NEW — `AgentRegistry.choose_target(decision, db)` |
| `backend/tools/governance_tool.py` | Richer tool descriptions; explicit anti-recursion note |
| `backend/core/tool_registry.py` | Tier-scoping review of `authorized_tiers` |
| Audit log / `_log` | Add `decision` action + `decision_id` correlation |

## 7. Out of scope

- Full distributed tracing / span system (deferred; light audit only).
- Replacing the message bus or Celery execution model.
- Changing the Constitution / governance voting thresholds.
