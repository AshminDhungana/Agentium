# 21.1.5 — Graceful Uncertainty Fallback & Anti-Hallucination Design

## Overview

This document describes the design for automatic uncertainty detection and graceful fallback when tool outputs are missing, erroneous, or ambiguous. The feature ensures agents request clarification via the existing hierarchy (`clarification_service.py`) rather than hallucinating results.

**Related to:** 
- Task 21.1.2 (Tool-Call Schema & Parameter Validation — already implemented)
- Task 21.1.3 (Multi-Step Context & State Retention — already implemented)  
- Task 21.1.4 (Output Format & Schema Compliance Enforcement — already implemented)
- `clarification_service.py` (existing hierarchy-based clarification)
- `clarification_tool.py` (existing Sovereign-facing clarification)

---

## Current State Analysis

| Component | Status | Notes |
|-----------|--------|-------|
| Tool execution | ✅ Complete | `run_tool_async()` returns structured results with `status`, `error`, `result` |
| Tool validation | ✅ Complete | `tool_registry` validates params via Pydantic before execution |
| Clarification hierarchy | ✅ Complete | `clarification_service.consult_supervisor()` + `escalate_clarification()` |
| Sovereign clarification tool | ✅ Complete | `request_user_clarification` tool for Human-in-the-loop |
| **Uncertainty detection** | ❌ **Missing** | No automatic detection of ambiguous/failed tool results |
| **Automatic fallback** | ❌ **Missing** | Agents don't auto-request clarification when uncertain |

---

## Design Philosophy

1. **Automatic & Transparent** — Uncertainty detected programmatically in the agentic loop; no LLM tokens spent on meta-reasoning
2. **Hierarchy-First** — Uses existing `clarification_service` chain (Supervisor → Escalation → Sovereign)
3. **In-Loop Resolution** — Clarification happens mid-execution, not after task failure
4. **Loop Prevention** — Tracks clarification attempts to avoid infinite escalation
5. **Provider-Centric** — Implemented in each provider's `generate_with_tools()` where tool results are available

---

## 1. Architecture

### 1.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ Provider.generate_with_tools() (OpenAICompatible, Anthropic)    │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Agentic Tool-Calling Loop (existing)                        │ │
│ │   1. LLM calls tools → executors return results             │ │
│ │   2. ✨ NEW: UncertaintyDetector.check(results)             │ │
│ │   3. ✨ NEW: If uncertain → ClarificationService consult    │ │
│ │   4. ✨ NEW: Inject guidance as system message              │ │
│ │   5. Loop continues with clarified context                  │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ ClarificationService (existing)                                 │
│   consult_supervisor(agent, question, context)                 │
│   escalate_clarification(agent, question, db, max_escalations) │
└─────────────────────────────────────────────────────────────────┘
                            ↓
                    Guidance injected into conversation
                            ↓
                    Agent continues with clarity
```

### 1.2 Data Flow

```
Tool execution batch completes
         ↓
results = [{"status": "error", "error": "..."}, {"status": "success", "result": {}}]
         ↓
UncertaintyDetector.analyze(results)
         ↓
    ┌────┴────┐
    │         │
Certain   Uncertain
    │         │
    ↓         ↓
Continue   ClarificationService.consult_supervisor(agent, db, question)
    │         ↓
    │    Guidance: "As your Lead: You were assigned to process X..."
    │         ↓
    │    Inject: {"role": "system", "content": "CLARIFICATION: ..."}
    │         ↓
    │    Increment clarification_attempts counter
    │         ↓
    │    Continue loop (max 2 clarification rounds per task)
    ↓
Next LLM turn sees clarification context
```

---

## 2. New Components

### 2.1 `UncertaintyDetector` — `backend/core/uncertainty_detector.py`

```python
class UncertaintyDetector:
    """
    Detects uncertainty signals in tool execution results.
    
    Trigger Conditions (any one matches):
    1. Tool status in ["error", "timeout", "cancelled"]
    2. Tool status == "success" but result is None, {}, or missing expected keys
    3. Multiple tools return conflicting information (same key, different values)
    4. Tool not found in registry (hallucinated tool name)
    5. All tools in a batch fail
    """

    # Expected result keys per tool (for detecting missing fields)
    TOOL_EXPECTED_KEYS: Dict[str, List[str]] = {
        "read_file": ["content"],
        "write_file": ["path", "written"],
        "execute_command": ["stdout", "stderr", "exit_code"],
        "browser_control": ["content", "url"],
        "nodriver_navigate": ["html", "url"],
        "deep_think_tool": ["reasoning", "conclusion"],
        # ... populated from tool_registry at runtime
    }

    @staticmethod
    def analyze(
        tool_results: List[Dict[str, Any]],
        agent: Agent,
        db: Session,
    ) -> Optional[UncertaintySignal]:
        """
        Analyze tool results for uncertainty.
        
        Returns:
            UncertaintySignal if uncertain, None if clear
        """
```

**UncertaintySignal dataclass:**
```python
@dataclass
class UncertaintySignal:
    reason: str                      # e.g. "tool_error", "empty_result", "conflicting_results"
    affected_tools: List[str]        # Names of tools that triggered uncertainty
    details: Dict[str, Any]          # Full context for clarification question
    suggested_question: str          # Pre-formulated question for supervisor
    severity: Literal["low", "medium", "high"]  # Determines escalation urgency
```

### 2.2 `ClarificationHandler` — `backend/services/clarification_handler.py`

```python
class ClarificationHandler:
    """
    Orchestrates clarification within the agentic loop.
    Handles: supervisor consult → escalation → guidance injection.
    """

    MAX_CLARIFICATION_ROUNDS = 2  # Prevent infinite loops per task execution

    def __init__(self, agent: Agent, db: Session):
        self.agent = agent
        self.db = db
        self.clarification_rounds = 0
        self.escalation_trail: List[Dict] = []

    async def handle_uncertainty(
        self,
        signal: UncertaintySignal,
        conversation: List[Dict[str, str]],
    ) -> Tuple[bool, Optional[str]]:
        """
        Attempt to resolve uncertainty via clarification.
        
        Returns:
            (resolved: bool, guidance_text: Optional[str])
            If resolved=True, guidance_text contains the injected system message.
            If resolved=False, max rounds exceeded or Sovereign unreachable.
        """
```

**Processing Logic:**
```
1. If clarification_rounds >= MAX_CLARIFICATION_ROUNDS:
     Return (False, "Max clarification rounds exceeded")
   
2. Call ClarificationService.consult_supervisor(agent, db, signal.suggested_question, signal.details)
   
3. If result has useful guidance:
     clarification_rounds += 1
     guidance = format_guidance(result)
     Return (True, guidance)
   
4. Else if escalation_available:
     Call ClarificationService.escalate_clarification(agent, signal.suggested_question, db)
     If escalation resolved:
         clarification_rounds += 1
         guidance = format_escalation_guidance(result)
         Return (True, guidance)
   
5. Return (False, None) — no clarification available
```

---

## 3. Provider Integration

### 3.1 `OpenAICompatibleProvider.generate_with_tools()` — Modified

**Location:** ~line 1100 in `model_provider.py` (after tool execution, before next loop iteration)

```python
# ── Existing: execute tool calls ──────────────────────────────────
tool_results = await asyncio.gather(*tool_tasks)

# ── NEW: Uncertainty Detection ──────────────────────────────────
from backend.core.uncertainty_detector import UncertaintyDetector
from backend.services.clarification_handler import ClarificationHandler

signal = UncertaintyDetector.analyze(tool_results, agent, db)
if signal:
    handler = ClarificationHandler(agent, db)
    resolved, guidance = await handler.handle_uncertainty(signal, conversation)
    if resolved:
        # Inject clarification as system message before next LLM turn
        conversation.append({
            "role": "system",
            "content": f"CLARIFICATION FROM SUPERVISOR:\n{guidance}\n\nPlease continue with this context."
        })
        # Track clarification in metadata for observability
        conversation[-1]["metadata"] = {"clarification_round": handler.clarification_rounds}
    else:
        # Max rounds exceeded — append warning and continue
        conversation.append({
            "role": "system", 
            "content": "WARNING: Unable to resolve uncertainty via clarification chain. Proceed with best judgment."
        })
```

### 3.2 `AnthropicProvider.generate_with_tools()` — When Implemented

Same pattern as OpenAI. Anthropic provider currently inherits `generate_with_tools()` from `OpenAICompatibleProvider` (line 1470+). Will need its own implementation when added.

---

## 4. Uncertainty Detection Rules

### 4.1 Trigger Conditions

| Condition | Detection Logic | Severity | Example Question |
|-----------|-----------------|----------|------------------|
| **Tool error** | `result["status"] in ["error", "timeout", "cancelled"]` | high | "My tool '{tool}' failed: {error}. What should I do?" |
| **Empty result** | `result["status"] == "success" and not result.get("result")` | medium | "Tool '{tool}' returned empty result. Is this expected?" |
| **Missing expected field** | `expected_keys - set(result.keys())` non-empty | medium | "Tool '{tool}' missing expected fields: {missing}. What do these mean?" |
| **Hallucinated tool** | `tool_name not in tool_registry.list_tools(tier)` | high | "I tried to call unknown tool '{tool}'. What tools are available?" |
| **Conflicting results** | Same key in multiple tool results with different values | low | "Tools {A,B} gave conflicting values for '{key}'. Which is correct?" |
| **All tools failed** | All results in batch have status != "success" | high | "All my tools failed. How should I proceed?" |

### 4.2 Pre-formulated Questions

The `UncertaintyDetector` generates specific questions based on the trigger:

```python
# Tool error
"My execution tool '{tool}' returned an error: {error}. 
 As my supervisor, what should I do next?"

# Empty result  
"Tool '{tool}' completed successfully but returned no data (empty result).
 Is this expected for this operation, or should I try a different approach?"

# Missing fields
"Tool '{tool}' returned a result but is missing expected fields: {missing_fields}.
 What do these fields represent and how should I obtain them?"

# Hallucinated tool
"I attempted to call tool '{tool}' which doesn't exist in my available tools ({available}).
 What is the correct tool for this operation?"

# Conflicting results
"Tools {tool_a} and {tool_b} returned conflicting values for '{key}':
  - {tool_a}: {value_a}
  - {tool_b}: {value_b}
Which source should I trust?"

# All failed
"All {count} tools I called failed. The errors were: {errors}.
 How should I proceed with this task?"
```

---

## 5. Integration Points

### 5.1 `ModelService.generate_with_agent_tools()` — Updated Signature (Optional)

Add optional tracking for clarification metadata:

```python
async def generate_with_agent_tools(
    ...
    # NEW: Track clarification in result
) -> Dict[str, Any]:
    # Result additions:
    return {
        "content": "...",
        # NEW FIELDS:
        "clarification_rounds": 0,      # Number of clarification cycles
        "clarification_signals": [],    # List of UncertaintySignal dicts
        "clarification_resolved": True, # Whether all uncertainties resolved
    }
```

### 5.2 `LLMClient.generate_with_tools()` — Pass Through

Pass clarification metadata through from provider result to caller.

### 5.3 `AgentOrchestrator.execute_task()` — Observability

Log clarification events for debugging:
```python
result = await llm_client.generate_with_tools(...)
if result.get("clarification_rounds", 0) > 0:
    logger.info(
        f"Task {task_id}: Agent {agent.agentium_id} required "
        f"{result['clarification_rounds']} clarification round(s)"
    )
```

---

## 6. Error Handling

| Scenario | Behavior |
|----------|----------|
| Clarification service DB error | Log warning, continue without clarification (fail open) |
| No parent/supervisor available | Try escalation; if Sovereign unreachable, continue with warning |
| Clarification loop detected (same signal repeats) | Stop after MAX_CLARIFICATION_ROUNDS, inject warning |
| Clarification guidance itself unclear | Count as unresolved, continue or escalate |
| Agent is Head of Council (no parent) | Skip to Sovereign escalation directly via `request_user_clarification` tool |

---

## 7. Testing Strategy

### 7.1 Unit Tests — `backend/tests/unit/test_uncertainty_detector.py`

| Test | Description |
|------|-------------|
| `test_tool_error_triggers` | Tool status="error" → UncertaintySignal(reason="tool_error") |
| `test_empty_result_triggers` | Tool success with empty result → signal |
| `test_missing_expected_keys` | Result missing known expected fields → signal |
| `test_hallucinated_tool` | Tool not in registry → signal |
| `test_conflicting_results` | Two tools, same key different values → signal |
| `test_all_tools_failed` | Batch all non-success → signal |
| `test_clean_results_no_signal` | All tools success with expected data → None |
| `test_severity_assignment` | Error=high, empty=medium, conflict=low |

### 7.2 Integration Tests — `backend/tests/integration/test_uncertainty_clarification.py`

| Test | Description |
|------|-------------|
| `test_clarification_injected_in_loop` | Tool error → clarification → guidance in next turn |
| `test_escalation_chain` | Supervisor unhelpful → escalation → higher guidance |
| `test_max_rounds_prevents_loop` | 3 rounds → stops, warning injected |
| `test_head_asks_sovereign` | Head (no parent) uses request_user_clarification tool |
| `test_task_agent_asks_lead` | Task agent → Lead → Council chain |
| `test_no_clarification_when_clear` | Normal execution unchanged |

### 7.3 Fixtures

```python
@pytest.fixture
def mock_agent_with_parent(db):
    """Agent with parent, ethos, and task history."""
    lead = create_agent(db, "20001", AgentType.LEAD_AGENT)
    task_agent = create_agent(db, "30001", AgentType.TASK_AGENT, parent=lead)
    # Add task history...
    return task_agent

@pytest.fixture
def tool_error_results():
    return [{"status": "error", "tool_name": "read_file", "error": "File not found"}]
```

---

## 8. Success Criteria

| Metric | Target |
|--------|--------|
| Uncertainty detection accuracy | >95% on known failure patterns |
| Clarification resolution rate | >80% of uncertainties resolved within 2 rounds |
| Loop prevention | 100% — no infinite clarification loops |
| Latency overhead | <200ms per clarification round |
| Backward compatibility | 100% — existing tests pass unchanged |
| Test coverage (new code) | ≥90% |

---

## 9. File Structure

```
backend/
├── core/
│   ├── uncertainty_detector.py          # NEW: UncertaintyDetector class
│   └── response_validator.py            # EXISTING
├── services/
│   ├── clarification_handler.py         # NEW: ClarificationHandler class
│   ├── clarification_service.py         # EXISTING (used by handler)
│   ├── model_provider.py                # UPDATED: OpenAICompatibleProvider.generate_with_tools()
│   └── chat_service.py                  # EXISTING (uses clarification_service for reincarnation)
├── tools/
│   └── clarification_tool.py            # EXISTING (Sovereign clarification)
│
backend/tests/
├── unit/
│   └── test_uncertainty_detector.py     # NEW
└── integration/
    └── test_uncertainty_clarification.py # NEW

docs/superpowers/specs/
    └── 2026-08-11-graceful-uncertainty-fallback-anti-hallucination-design.md  # THIS FILE
```

---

## 10. Dependencies

- **Existing**: `clarification_service.py`, `clarification_tool.py`, `tool_registry`, `run_tool_async`
- **No new external dependencies** — pure Python

---

## 11. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Infinite clarification loops | Hard limit `MAX_CLARIFICATION_ROUNDS=2` per task execution |
| Clarification adds significant latency | Async calls, timeout on clarification_service, fail-open |
| Supervisor gives unhelpful guidance | Escalation chain; max 2 levels before Sovereign |
| False positives on "empty result" | Only flag if tool typically returns data (configurable per-tool) |
| Breaking existing provider behavior | Feature only activates when uncertainty detected; zero overhead otherwise |
| DB session issues in provider | ClarificationHandler accepts db session; provider already has it |

---

## 12. Future Extensions

| Feature | Description |
|---------|-------------|
| Learned uncertainty patterns | Track which tools/conditions cause uncertainty; auto-improve prompts |
| Clarification caching | Cache supervisor guidance for common uncertainty patterns |
| Metrics dashboard | Track clarification frequency, resolution rates, escalation paths |
| Proactive clarification | Agent asks for clarification BEFORE calling risky tools |
| Multi-modal uncertainty | Detect uncertainty in image/audio tool results |

---

## 13. Approval

> **Design approved by:** ____________________ **Date:** __________
>
> **Implementation plan to follow:** `writing-plans` skill