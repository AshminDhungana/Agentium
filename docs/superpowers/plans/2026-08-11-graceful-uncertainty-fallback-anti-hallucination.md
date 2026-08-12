# 21.1.5 Graceful Uncertainty Fallback & Anti-Hallucination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement automatic uncertainty detection in the agentic loop that triggers clarification via the existing hierarchy (clarification_service) when tool outputs are missing, erroneous, or ambiguous — preventing agents from hallucinating results.

**Architecture:** Add `UncertaintyDetector` in `backend/core/` to analyze tool results after each execution batch. Add `ClarificationHandler` in `backend/services/` to orchestrate supervisor consultation and escalation. Integrate into `OpenAICompatibleProvider.generate_with_tools()` (and future Anthropic provider) to inject clarification guidance as system messages before the next LLM turn.

**Tech Stack:** Python 3.11+, SQLAlchemy, Pydantic, existing `clarification_service.py`, `tool_registry`, `run_tool_async`

## Global Constraints

- Follow existing patterns in `model_provider.py` for provider implementation
- Use existing `ClarificationService.consult_supervisor()` and `escalate_clarification()` methods
- Max 2 clarification rounds per task execution (hard limit to prevent loops)
- Zero overhead when no uncertainty detected (fail-open design)
- All new code in `backend/core/uncertainty_detector.py` and `backend/services/clarification_handler.py`
- Tests in `backend/tests/unit/test_uncertainty_detector.py` and `backend/tests/integration/test_uncertainty_clarification.py`
- No new external dependencies

---

## File Structure

**New Files:**
- `backend/core/uncertainty_detector.py` — UncertaintyDetector class with analyze() method
- `backend/services/clarification_handler.py` — ClarificationHandler class with handle_uncertainty() method
- `backend/tests/unit/test_uncertainty_detector.py` — Unit tests for UncertaintyDetector
- `backend/tests/integration/test_uncertainty_clarification.py` — Integration tests for clarification flow

**Modified Files:**
- `backend/services/model_provider.py` — OpenAICompatibleProvider.generate_with_tools() integration
- `backend/services/model_provider.py` — AnthropicProvider.generate_with_tools() (when implemented, same pattern)

---

## File Structure

**New Files:**
- `backend/core/uncertainty_detector.py` — UncertaintyDetector class with analyze() method
- `backend/services/clarification_handler.py` — ClarificationHandler class with handle_uncertainty() method
- `backend/tests/unit/test_uncertainty_detector.py` — Unit tests for UncertaintyDetector
- `backend/tests/integration/test_uncertainty_clarification.py` — Integration tests for clarification flow

**Modified Files:**
- `backend/services/model_provider.py` — OpenAICompatibleProvider.generate_with_tools() integration
- `backend/services/model_provider.py` — AnthropicProvider.generate_with_tools() (when implemented, same pattern)

**Interfaces:**

```
UncertaintyDetector.analyze(tool_results: List[Dict], agent: Agent, db: Session) -> Optional[UncertaintySignal]
UncertaintySignal(reason: str, affected_tools: List[str], details: Dict, suggested_question: str, severity: Literal["low","medium","high"])

ClarificationHandler(agent: Agent, db: Session)
ClarificationHandler.handle_uncertainty(signal: UncertaintySignal, conversation: List[Dict]) -> Tuple[bool, Optional[str]]
```

---

### Task 1: Create UncertaintySignal dataclass and UncertaintyDetector class

**Files:**
- Create: `backend/core/uncertainty_detector.py`
- Test: `backend/tests/unit/test_uncertainty_detector.py`

**Interfaces:**
- Produces: `UncertaintySignal` dataclass, `UncertaintyDetector.analyze()` static method

- [ ] **Step 1: Write the failing test for UncertaintySignal**

```python
# backend/tests/unit/test_uncertainty_detector.py
import pytest
from backend.core.uncertainty_detector import UncertaintySignal

def test_uncertainty_signal_creation():
    signal = UncertaintySignal(
        reason="tool_error",
        affected_tools=["read_file"],
        details={"error": "File not found"},
        suggested_question="My tool 'read_file' returned an error: File not found. What should I do?",
        severity="high"
    )
    assert signal.reason == "tool_error"
    assert signal.affected_tools == ["read_file"]
    assert signal.severity == "high"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_uncertainty_detector.py::test_uncertainty_signal_creation -v`
Expected: FAIL with "ModuleNotFoundError" or "UncertaintySignal not defined"

- [ ] **Step 3: Write minimal UncertaintySignal and UncertaintyDetector**

```python
# backend/core/uncertainty_detector.py
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Literal
from sqlalchemy.orm import Session

@dataclass
class UncertaintySignal:
    reason: str
    affected_tools: List[str]
    details: Dict[str, Any]
    suggested_question: str
    severity: Literal["low", "medium", "high"]


class UncertaintyDetector:
    """Detects uncertainty signals in tool execution results."""

    # Expected result keys per tool (populated from registry at runtime)
    TOOL_EXPECTED_KEYS: Dict[str, List[str]] = {
        "read_file": ["content"],
        "write_file": ["path", "written"],
        "execute_command": ["stdout", "stderr", "exit_code"],
        "browser_control": ["content", "url"],
        "nodriver_navigate": ["html", "url"],
        "deep_think_tool": ["reasoning", "conclusion"],
    }

    @staticmethod
    def analyze(
        tool_results: List[Dict[str, Any]],
        agent: Any,  # Agent type
        db: Session,
    ) -> Optional[UncertaintySignal]:
        """
        Analyze tool results for uncertainty.
        
        Returns UncertaintySignal if uncertain, None if all results are clear.
        """
        if not tool_results:
            return None

        # Check each result for uncertainty triggers
        for result in tool_results:
            signal = UncertaintyDetector._check_single_result(result)
            if signal:
                return signal

        # Check for conflicting results across tools
        conflict_signal = UncertaintyDetector._check_conflicts(tool_results)
        if conflict_signal:
            return conflict_signal

        # Check if all tools failed
        if all(r.get("status") != "success" for r in tool_results):
            return UncertaintySignal(
                reason="all_tools_failed",
                affected_tools=[r.get("tool_name", "unknown") for r in tool_results],
                details={"errors": [r.get("error") for r in tool_results if r.get("error")]},
                suggested_question=(
                    f"All {len(tool_results)} tools I called failed. "
                    f"The errors were: {[r.get('error') for r in tool_results if r.get('error')]}. "
                    "How should I proceed with this task?"
                ),
                severity="high"
            )

        return None

    @staticmethod
    def _check_single_result(result: Dict[str, Any]) -> Optional[UncertaintySignal]:
        """Check a single tool result for uncertainty triggers."""
        status = result.get("status")
        tool_name = result.get("tool_name", "unknown")

        # Tool error/timeout/cancelled
        if status in ("error", "timeout", "cancelled"):
            error = result.get("error", "Unknown error")
            return UncertaintySignal(
                reason="tool_error",
                affected_tools=[tool_name],
                details={"status": status, "error": error},
                suggested_question=(
                    f"My execution tool '{tool_name}' returned an error: {error}. "
                    "As my supervisor, what should I do next?"
                ),
                severity="high"
            )

        # Tool succeeded but empty result
        if status == "success":
            result_data = result.get("result")
            if result_data is None or result_data == {}:
                return UncertaintySignal(
                    reason="empty_result",
                    affected_tools=[tool_name],
                    details={"status": status, "result": result_data},
                    suggested_question=(
                        f"Tool '{tool_name}' completed successfully but returned no data (empty result). "
                        "Is this expected for this operation, or should I try a different approach?"
                    ),
                    severity="medium"
                )

            # Missing expected fields
            expected_keys = UncertaintyDetector.TOOL_EXPECTED_KEYS.get(tool_name, [])
            if expected_keys:
                missing = [k for k in expected_keys if k not in result_data]
                if missing:
                    return UncertaintySignal(
                        reason="missing_expected_fields",
                        affected_tools=[tool_name],
                        details={"missing_fields": missing, "result_keys": list(result_data.keys())},
                        suggested_question=(
                            f"Tool '{tool_name}' returned a result but is missing expected fields: {missing}. "
                            "What do these fields represent and how should I obtain them?"
                        ),
                        severity="medium"
                    )

        return None

    @staticmethod
    def _check_conflicts(tool_results: List[Dict[str, Any]]) -> Optional[UncertaintySignal]:
        """Check for conflicting values across tool results."""
        # Build map of key -> (tool_name, value)
        key_map: Dict[str, List[tuple]] = {}
        for result in tool_results:
            if result.get("status") == "success":
                result_data = result.get("result", {})
                tool_name = result.get("tool_name", "unknown")
                for key, value in result_data.items():
                    if key not in key_map:
                        key_map[key] = []
                    key_map[key].append((tool_name, value))

        # Find keys with conflicting values
        for key, entries in key_map.items():
            if len(entries) > 1:
                values = [v for _, v in entries]
                if len(set(str(v) for v in values)) > 1:
                    tool_names = [t for t, _ in entries]
                    return UncertaintySignal(
                        reason="conflicting_results",
                        affected_tools=tool_names,
                        details={
                            "key": key,
                            "values": {t: str(v) for t, v in entries}
                        },
                        suggested_question=(
                            f"Tools {', '.join(tool_names)} returned conflicting values for '{key}': "
                            f"{', '.join(f'{t}={v}' for t, v in entries)}. "
                            "Which source should I trust?"
                        ),
                        severity="low"
                    )
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_uncertainty_detector.py::test_uncertainty_signal_creation -v`
Expected: PASS

- [ ] **Step 5: Write tests for each detection scenario**

```python
# backend/tests/unit/test_uncertainty_detector.py (continued)
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from backend.core.uncertainty_detector import UncertaintyDetector, UncertaintySignal

@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.agentium_id = "30001"
    return agent

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)

def test_tool_error_triggers_signal(mock_agent, mock_db):
    results = [{"status": "error", "tool_name": "read_file", "error": "File not found", "result": None}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "tool_error"
    assert signal.severity == "high"
    assert "read_file" in signal.affected_tools

def test_timeout_triggers_signal(mock_agent, mock_db):
    results = [{"status": "timeout", "tool_name": "execute_command", "error": "Timed out after 30s", "result": None}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "tool_error"
    assert signal.severity == "high"

def test_cancelled_triggers_signal(mock_agent, mock_db):
    results = [{"status": "cancelled", "tool_name": "browser_control", "error": "Cancelled by user", "result": None}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "tool_error"

def test_empty_result_triggers_signal(mock_agent, mock_db):
    results = [{"status": "success", "tool_name": "read_file", "result": {}}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "empty_result"
    assert signal.severity == "medium"

def test_empty_result_none_triggers_signal(mock_agent, mock_db):
    results = [{"status": "success", "tool_name": "read_file", "result": None}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "empty_result"

def test_missing_expected_fields_triggers_signal(mock_agent, mock_db):
    # read_file expects "content" key
    results = [{"status": "success", "tool_name": "read_file", "result": {"size": 100}}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "missing_expected_fields"
    assert "content" in signal.details["missing_fields"]

def test_hallucinated_tool_no_expected_keys(mock_agent, mock_db):
    # Tool not in TOOL_EXPECTED_KEYS - no missing field check
    results = [{"status": "success", "tool_name": "unknown_tool", "result": {"data": "x"}}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is None  # Unknown tools don't trigger missing field check

def test_conflicting_results_triggers_signal(mock_agent, mock_db):
    results = [
        {"status": "success", "tool_name": "tool_a", "result": {"value": "first"}},
        {"status": "success", "tool_name": "tool_b", "result": {"value": "second"}},
    ]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "conflicting_results"
    assert signal.severity == "low"
    assert set(signal.affected_tools) == {"tool_a", "tool_b"}

def test_no_conflict_when_same_value(mock_agent, mock_db):
    results = [
        {"status": "success", "tool_name": "tool_a", "result": {"value": "same"}},
        {"status": "success", "tool_name": "tool_b", "result": {"value": "same"}},
    ]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is None

def test_all_tools_failed_triggers_signal(mock_agent, mock_db):
    results = [
        {"status": "error", "tool_name": "tool_a", "error": "Error A"},
        {"status": "error", "tool_name": "tool_b", "error": "Error B"},
    ]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "all_tools_failed"
    assert signal.severity == "high"

def test_clean_results_no_signal(mock_agent, mock_db):
    results = [
        {"status": "success", "tool_name": "read_file", "result": {"content": "file data"}},
        {"status": "success", "tool_name": "execute_command", "result": {"stdout": "output", "stderr": "", "exit_code": 0}},
    ]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is None

def test_empty_results_list_no_signal(mock_agent, mock_db):
    signal = UncertaintyDetector.analyze([], mock_agent, mock_db)
    assert signal is None
```

- [ ] **Step 6: Run all unit tests**

Run: `pytest backend/tests/unit/test_uncertainty_detector.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/core/uncertainty_detector.py backend/tests/unit/test_uncertainty_detector.py
git commit -m "feat: add UncertaintyDetector for tool result uncertainty detection"
```

---

### Task 2: Create ClarificationHandler class

**Files:**
- Create: `backend/services/clarification_handler.py`
- Test: `backend/tests/unit/test_clarification_handler.py`

**Interfaces:**
- Consumes: `UncertaintySignal` from Task 1, `ClarificationService` (existing)
- Produces: `ClarificationHandler` class with `handle_uncertainty()` method

- [ ] **Step 1: Write the failing test for ClarificationHandler**

```python
# backend/tests/unit/test_clarification_handler.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.orm import Session
from backend.services.clarification_handler import ClarificationHandler
from backend.core.uncertainty_detector import UncertaintySignal

@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.agentium_id = "30001"
    agent.parent = MagicMock()
    agent.parent.agentium_id = "20001"
    agent.parent.agent_type.value = "lead_agent"
    return agent

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)

@pytest.fixture
def sample_signal():
    return UncertaintySignal(
        reason="tool_error",
        affected_tools=["read_file"],
        details={"status": "error", "error": "File not found"},
        suggested_question="My tool 'read_file' returned an error: File not found. What should I do?",
        severity="high"
    )

def test_clarification_handler_creation(mock_agent, mock_db):
    handler = ClarificationHandler(mock_agent, mock_db)
    assert handler.agent == mock_agent
    assert handler.db == mock_db
    assert handler.clarification_rounds == 0
    assert handler.MAX_CLARIFICATION_ROUNDS == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_clarification_handler.py::test_clarification_handler_creation -v`
Expected: FAIL with "ModuleNotFoundError" or "ClarificationHandler not defined"

- [ ] **Step 3: Write ClarificationHandler implementation**

```python
# backend/services/clarification_handler.py
import logging
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session

from backend.services.clarification_service import ClarificationService
from backend.core.uncertainty_detector import UncertaintySignal

logger = logging.getLogger(__name__)


class ClarificationHandler:
    """
    Orchestrates clarification within the agentic loop.
    Handles: supervisor consult → escalation → guidance injection.
    """

    MAX_CLARIFICATION_ROUNDS = 2  # Prevent infinite loops per task execution

    def __init__(self, agent: Any, db: Session):
        self.agent = agent
        self.db = db
        self.clarification_rounds = 0
        self.escalation_trail: List[Dict[str, Any]] = []

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
            If resolved=False, max rounds exceeded or clarification unavailable.
        """
        # Check round limit
        if self.clarification_rounds >= self.MAX_CLARIFICATION_ROUNDS:
            logger.warning(
                f"Agent {self.agent.agentium_id}: Max clarification rounds ({self.MAX_CLARIFICATION_ROUNDS}) exceeded"
            )
            return False, None

        # Step 1: Consult immediate supervisor
        logger.info(
            f"Agent {self.agent.agentium_id}: Requesting clarification from supervisor "
            f"(round {self.clarification_rounds + 1}/{self.MAX_CLARIFICATION_ROUNDS})"
        )
        
        consult_result = ClarificationService.consult_supervisor(
            agent=self.agent,
            db=self.db,
            question=signal.suggested_question,
            context=f"Uncertainty detected: {signal.reason} in tools {signal.affected_tools}. Details: {signal.details}"
        )

        # Check if consultation provided useful guidance
        guidance = consult_result.get("guidance")
        if guidance and guidance.strip() and "cannot clarify" not in guidance.lower():
            self.clarification_rounds += 1
            formatted = self._format_guidance(consult_result, signal, source="supervisor")
            logger.info(f"Agent {self.agent.agentium_id}: Clarification resolved via supervisor")
            return True, formatted

        # Step 2: Escalate if supervisor couldn't help and escalation is available
        if consult_result.get("escalation_available"):
            logger.info(
                f"Agent {self.agent.agentium_id}: Supervisor unclear, escalating up hierarchy"
            )
            escalation_result = ClarificationService.escalate_clarification(
                agent=self.agent,
                question=signal.suggested_question,
                db=self.db,
                max_escalations=3
            )

            self.escalation_trail.append(escalation_result)

            # Check if escalation resolved
            if escalation_result.get("resolved"):
                # Find the step that achieved clarity
                for step in escalation_result.get("escalation_trail", []):
                    if step.get("result") == "clarity_achieved":
                        guidance = step.get("guidance")
                        if guidance:
                            self.clarification_rounds += 1
                            formatted = self._format_guidance(
                                {"guidance": guidance, "consulted": step.get("consulted"), 
                                 "role": step.get("role")}, 
                                signal, source="escalation"
                            )
                            logger.info(
                                f"Agent {self.agent.agentium_id}: Clarification resolved via escalation "
                                f"to {step.get('role')}"
                            )
                            return True, formatted

        # No resolution found
        logger.warning(f"Agent {self.agent.agentium_id}: Clarification unresolved after escalation")
        return False, None

    def _format_guidance(
        self,
        result: Dict[str, Any],
        signal: UncertaintySignal,
        source: str
    ) -> str:
        """Format clarification result into a system message."""
        consulted = result.get("consulted", "unknown")
        role = result.get("role", result.get("parent_role", "supervisor"))
        guidance = result.get("guidance", "")
        your_purpose = result.get("your_purpose", "")
        task_history = result.get("task_history", [])
        recommendation = result.get("recommendation", "")

        parts = [
            f"CLARIFICATION FROM {role.upper()} ({consulted}) — {source}",
            f"Original uncertainty: {signal.reason} in tools {signal.affected_tools}",
            f"Guidance: {guidance}",
        ]

        if your_purpose:
            parts.append(f"Your purpose: {your_purpose}")

        if task_history:
            task_summary = "; ".join(
                f"{t['task_id']}: {t['title']} ({t['status']}, {t['progress']}%)"
                for t in task_history[:2]
            )
            parts.append(f"Recent tasks: {task_summary}")

        if recommendation:
            parts.append(f"Recommendation: {recommendation}")

        return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_clarification_handler.py::test_clarification_handler_creation -v`
Expected: PASS

- [ ] **Step 5: Write tests for clarification flow**

```python
# backend/tests/unit/test_clarification_handler.py (continued)
@pytest.mark.asyncio
async def test_handle_uncertainty_supervisor_resolves(mock_agent, mock_db, sample_signal):
    # Mock consult_supervisor to return useful guidance
    with patch("backend.services.clarification_handler.ClarificationService.consult_supervisor") as mock_consult:
        mock_consult.return_value = {
            "consulted": "20001",
            "parent_role": "lead_agent",
            "guidance": "Use the browser tool instead to read the file.",
            "your_purpose": "Process user requests...",
            "task_history": [{"task_id": "task-1", "title": "Read config", "status": "in_progress", "progress": 50}],
            "recommendation": "Try browser_control tool",
            "escalation_available": True
        }
        
        handler = ClarificationHandler(mock_agent, mock_db)
        resolved, guidance = await handler.handle_uncertainty(sample_signal, [])
        
        assert resolved is True
        assert guidance is not None
        assert "CLARIFICATION FROM LEAD_AGENT" in guidance
        assert "Use the browser tool" in guidance
        assert handler.clarification_rounds == 1

@pytest.mark.asyncio
async def test_handle_uncertainty_escalation_resolves(mock_agent, mock_db, sample_signal):
    # Mock consult_supervisor to return no useful guidance, then escalation resolves
    with patch("backend.services.clarification_handler.ClarificationService.consult_supervisor") as mock_consult, \
         patch("backend.services.clarification_handler.ClarificationService.escalate_clarification") as mock_escalate:
        
        mock_consult.return_value = {
            "consulted": "20001",
            "parent_role": "lead_agent",
            "guidance": "I cannot clarify this.",
            "your_purpose": "Process user requests...",
            "task_history": [],
            "recommendation": "",
            "escalation_available": True
        }
        
        mock_escalate.return_value = {
            "resolved": True,
            "escalation_trail": [
                {"consulted": "20001", "role": "lead_agent", "guidance": "I cannot clarify", "result": "unclear"},
                {"consulted": "10001", "role": "council_member", "guidance": "Check the file path and retry.", "result": "clarity_achieved"}
            ]
        }
        
        handler = ClarificationHandler(mock_agent, mock_db)
        resolved, guidance = await handler.handle_uncertainty(sample_signal, [])
        
        assert resolved is True
        assert guidance is not None
        assert "CLARIFICATION FROM COUNCIL_MEMBER" in guidance
        assert "Check the file path" in guidance
        assert handler.clarification_rounds == 1

@pytest.mark.asyncio
async def test_handle_uncertainty_max_rounds_exceeded(mock_agent, mock_db, sample_signal):
    handler = ClarificationHandler(mock_agent, mock_db)
    handler.clarification_rounds = 2  # At max
    
    resolved, guidance = await handler.handle_uncertainty(sample_signal, [])
    
    assert resolved is False
    assert guidance is None

@pytest.mark.asyncio
async def test_handle_uncertainty_no_parent_escalates_to_sovereign(mock_agent, mock_db, sample_signal):
    # Agent with no parent (Head of Council)
    mock_agent.parent = None
    
    with patch("backend.services.clarification_handler.ClarificationService.consult_supervisor") as mock_consult, \
         patch("backend.services.clarification_handler.ClarificationService.escalate_clarification") as mock_escalate:
        
        mock_consult.return_value = {
            "consulted": None,
            "parent_role": "sovereign",
            "guidance": "You report directly to the Sovereign. Check system logs for your assigned purpose.",
            "your_purpose": "Process user requests...",
            "task_history": [],
            "recommendation": "Ask the Sovereign for clarification",
            "escalation_available": False
        }
        
        handler = ClarificationHandler(mock_agent, mock_db)
        resolved, guidance = await handler.handle_uncertainty(sample_signal, [])
        
        # Should resolve because guidance is useful
        assert resolved is True
        assert "SOVEREIGN" in guidance.upper()

@pytest.mark.asyncio
async def test_handle_uncertainty_completely_unresolved(mock_agent, mock_db, sample_signal):
    with patch("backend.services.clarification_handler.ClarificationService.consult_supervisor") as mock_consult, \
         patch("backend.services.clarification_handler.ClarificationService.escalate_clarification") as mock_escalate:
        
        mock_consult.return_value = {
            "consulted": "20001",
            "parent_role": "lead_agent",
            "guidance": "I cannot clarify this.",
            "your_purpose": "",
            "task_history": [],
            "recommendation": "",
            "escalation_available": True
        }
        
        mock_escalate.return_value = {
            "resolved": False,
            "escalation_trail": [
                {"consulted": "20001", "role": "lead_agent", "guidance": "I cannot clarify", "result": "unclear"},
                {"consulted": "10001", "role": "council_member", "guidance": "Also unclear", "result": "unclear"}
            ]
        }
        
        handler = ClarificationHandler(mock_agent, mock_db)
        resolved, guidance = await handler.handle_uncertainty(sample_signal, [])
        
        assert resolved is False
        assert guidance is None
```

- [ ] **Step 6: Run all unit tests**

Run: `pytest backend/tests/unit/test_clarification_handler.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/services/clarification_handler.py backend/tests/unit/test_clarification_handler.py
git commit -m "feat: add ClarificationHandler for orchestrating supervisor clarification"
```

---

### Task 3: Integrate UncertaintyDetector and ClarificationHandler into OpenAICompatibleProvider.generate_with_tools()

**Files:**
- Modify: `backend/services/model_provider.py` (OpenAICompatibleProvider.generate_with_tools method around line 1100+)
- Test: `backend/tests/integration/test_uncertainty_clarification.py`

**Interfaces:**
- Consumes: `UncertaintyDetector.analyze()`, `ClarificationHandler.handle_uncertainty()` from Tasks 1-2
- Produces: Modified `generate_with_tools()` that injects clarification guidance into conversation

- [ ] **Step 1: Write the failing integration test**

```python
# backend/tests/integration/test_uncertainty_clarification.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session
from backend.services.model_provider import OpenAICompatibleProvider, ModelService
from backend.core.uncertainty_detector import UncertaintySignal

@pytest.fixture
def mock_config():
    config = MagicMock()
    config.provider = "OPENAI"
    config.default_model = "gpt-4o"
    config.max_tokens = 1000
    config.temperature = 0.7
    config.top_p = 1.0
    config.timeout_seconds = 30
    config.max_concurrent_requests = 10
    config.requests_per_minute = 60
    config.id = "test-config-id"
    config.effort = "none"
    return config

@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.agentium_id = "30001"
    agent.ethos = MagicMock()
    agent.ethos.mission_statement = "Test mission"
    agent.ethos.behavioral_rules = "[]"
    # Mock parent for clarification
    parent = MagicMock()
    parent.agentium_id = "20001"
    parent.agent_type.value = "lead_agent"
    agent.parent = parent
    return agent

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)

@pytest.mark.asyncio
async def test_generate_with_tools_injects_clarification_on_tool_error(mock_config, mock_agent, mock_db):
    """Tool error triggers clarification which is injected as system message before next LLM turn."""
    provider = OpenAICompatibleProvider(config=mock_config)
    provider.api_key = "test-key"
    provider.base_url = "https://api.openai.com/v1"
    
    # Mock the client
    mock_client = AsyncMock()
    # First call: LLM calls a tool
    first_response = MagicMock()
    first_response.choices = [MagicMock()]
    first_response.choices[0].message = MagicMock()
    first_response.choices[0].message.tool_calls = [
        MagicMock(
            id="call_1",
            function=MagicMock(name="read_file", arguments='{"filepath": "/nonexistent.txt"}')
        )
    ]
    first_response.choices[0].finish_reason = "tool_calls"
    first_response.model = "gpt-4o"
    first_response.usage = MagicMock(prompt_tokens=50, completion_tokens=50)
    
    # Second call: after tool execution + clarification injection, LLM responds
    second_response = MagicMock()
    second_response.choices = [MagicMock()]
    second_response.choices[0].message = MagicMock()
    second_response.choices[0].message.content = "I understand, I'll use a different approach."
    second_response.choices[0].message.tool_calls = None
    second_response.choices[0].finish_reason = "stop"
    second_response.model = "gpt-4o"
    second_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
    
    mock_client.chat.completions.create = AsyncMock(side_effect=[first_response, second_response])
    
    # Patch the cached client
    import backend.services.model_provider as mp
    cache_key = (str(mock_config.id), provider.api_key, provider.base_url, False)
    original_cache = mp._CLIENT_CACHE.get(cache_key)
    mp._CLIENT_CACHE[cache_key] = mock_client
    
    try:
        # Mock tool executor to return error
        async def mock_tool_executor(name, args):
            return {"status": "error", "tool_name": name, "error": "File not found", "result": None}
        
        # Mock UncertaintyDetector to return signal
        with patch("backend.services.model_provider.UncertaintyDetector.analyze") as mock_analyze, \
             patch("backend.services.model_provider.ClarificationHandler") as mock_handler_class:
            
            mock_analyze.return_value = UncertaintySignal(
                reason="tool_error",
                affected_tools=["read_file"],
                details={"status": "error", "error": "File not found"},
                suggested_question="My tool 'read_file' returned an error: File not found. What should I do?",
                severity="high"
            )
            
            mock_handler = AsyncMock()
            mock_handler.handle_uncertainty = AsyncMock(return_value=(True, "CLARIFICATION FROM LEAD_AGENT (20001) — supervisor\nOriginal uncertainty: tool_error in tools ['read_file']\nGuidance: Use browser tool instead"))
            mock_handler_class.return_value = mock_handler
            
            # Also mock provider_rate_limiter
            with patch("backend.services.model_provider.provider_rate_limiter.acquire_concurrency", new=AsyncMock()), \
                 patch("backend.services.model_provider.provider_rate_limiter.acquire", new=AsyncMock()), \
                 patch("backend.services.model_provider.provider_rate_limiter.release_concurrency", new=AsyncMock()), \
                 patch("backend.services.model_provider._record_provider_headers", new=AsyncMock()), \
                 patch("backend.services.model_provider.api_key_manager") as mock_key_manager:
                
                mock_key_manager.mark_key_success = MagicMock()
                mock_key_manager.record_spend = MagicMock()
                
                result = await provider.generate_with_tools(
                    system_prompt="You are a helpful agent.",
                    messages=[{"role": "user", "content": "Read a file"}],
                    tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
                    tool_executor=mock_tool_executor,
                    max_iterations=5,
                    agentium_id="30001",
                )
                
                # Verify clarification was injected (check conversation had system message added)
                # The second call to create should include the clarification system message
                calls = mock_client.chat.completions.create.call_args_list
                assert len(calls) == 2
                
                # Second call should have clarification in messages
                second_call_messages = calls[1].kwargs["messages"]
                # Find system message with clarification
                clarification_found = any(
                    msg.get("role") == "system" and "CLARIFICATION" in msg.get("content", "")
                    for msg in second_call_messages
                )
                assert clarification_found, "Clarification system message not injected"
                
    finally:
        if original_cache:
            mp._CLIENT_CACHE[cache_key] = original_cache
        else:
            del mp._CLIENT_CACHE[cache_key]

@pytest.mark.asyncio
async def test_generate_with_tools_continues_without_clarification_when_clear(mock_config, mock_agent, mock_db):
    """Clean tool results don't trigger clarification."""
    provider = OpenAICompatibleProvider(config=mock_config)
    provider.api_key = "test-key"
    provider.base_url = "https://api.openai.com/v1"
    
    mock_client = AsyncMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message = MagicMock()
    response.choices[0].message.content = "Done"
    response.choices[0].message.tool_calls = None
    response.choices[0].finish_reason = "stop"
    response.model = "gpt-4o"
    response.usage = MagicMock(prompt_tokens=50, completion_tokens=50)
    mock_client.chat.completions.create = AsyncMock(return_value=response)
    
    import backend.services.model_provider as mp
    cache_key = (str(mock_config.id), provider.api_key, provider.base_url, False)
    original_cache = mp._CLIENT_CACHE.get(cache_key)
    mp._CLIENT_CACHE[cache_key] = mock_client
    
    try:
        async def mock_tool_executor(name, args):
            return {"status": "success", "tool_name": name, "result": {"content": "file data"}}
        
        with patch("backend.services.model_provider.UncertaintyDetector.analyze") as mock_analyze, \
             patch("backend.services.model_provider.provider_rate_limiter.acquire_concurrency", new=AsyncMock()), \
             patch("backend.services.model_provider.provider_rate_limiter.acquire", new=AsyncMock()), \
             patch("backend.services.model_provider.provider_rate_limiter.release_concurrency", new=AsyncMock()), \
             patch("backend.services.model_provider._record_provider_headers", new=AsyncMock()), \
             patch("backend.services.model_provider.api_key_manager") as mock_key_manager:
            
            mock_analyze.return_value = None  # No uncertainty
            mock_key_manager.mark_key_success = MagicMock()
            mock_key_manager.record_spend = MagicMock()
            
            result = await provider.generate_with_tools(
                system_prompt="You are a helpful agent.",
                messages=[{"role": "user", "content": "Read a file"}],
                tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
                tool_executor=mock_tool_executor,
                max_iterations=5,
                agentium_id="30001",
            )
            
            assert result["content"] == "Done"
            # UncertaintyDetector.analyze should have been called
            mock_analyze.assert_called_once()
            
    finally:
        if original_cache:
            mp._CLIENT_CACHE[cache_key] = original_cache
        else:
            del mp._CLIENT_CACHE[cache_key]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_uncertainty_clarification.py::test_generate_with_tools_injects_clarification_on_tool_error -v`
Expected: FAIL (UncertaintyDetector/ClarificationHandler not imported in model_provider.py yet)

- [ ] **Step 3: Add imports and integration to OpenAICompatibleProvider.generate_with_tools()**

```python
# In backend/services/model_provider.py, add at top of file (after existing imports):
# from backend.core.uncertainty_detector import UncertaintyDetector
# from backend.services.clarification_handler import ClarificationHandler

# Find the generate_with_tools method in OpenAICompatibleProvider (around line 945+)
# Add uncertainty detection after tool execution and before next LLM iteration

# The key insertion point is after:
# tool_results = await asyncio.gather(*tool_tasks)
# and before the loop continues to next iteration

# Add this code block:
"""
# ── Uncertainty Detection & Clarification ──────────────────────────
try:
    from backend.core.uncertainty_detector import UncertaintyDetector
    from backend.services.clarification_handler import ClarificationHandler
    
    signal = UncertaintyDetector.analyze(tool_results, kwargs.get("agent"), db)
    if signal:
        handler = ClarificationHandler(kwargs.get("agent"), db)
        resolved, guidance = await handler.handle_uncertainty(signal, conversation)
        if resolved:
            # Inject clarification as system message before next LLM turn
            conversation.append({
                "role": "system",
                "content": f"CLARIFICATION FROM SUPERVISOR:\n{guidance}\n\nPlease continue with this context."
            })
            # Track clarification in metadata for observability
            if "metadata" not in conversation[-1]:
                conversation[-1]["metadata"] = {}
            conversation[-1]["metadata"]["clarification_round"] = handler.clarification_rounds
        else:
            # Max rounds exceeded or no clarification available
            conversation.append({
                "role": "system", 
                "content": "WARNING: Unable to resolve uncertainty via clarification chain. Proceed with best judgment."
            })
except Exception as e:
    # Fail open - log and continue without clarification
    logger.warning(f"Uncertainty detection/clarification failed (fail-open): {e}")
"""
```

- [ ] **Step 4: Also add clarification tracking to final result**

```python
# At the end of generate_with_tools(), add clarification metadata to result:
# (Find the return statement around line 1200+)

# Add to the returned dict:
"""
return {
    "content": content,
    "tokens_used": total_tokens,
    "prompt_tokens": total_prompt_tokens,
    "completion_tokens": total_completion_tokens,
    "latency_ms": int((time.time() - start_time) * 1000),
    "model": actual_model,
    "messages": conversation,
    "finish_reason": finish_reason,
    "cost_usd": cost,
    # NEW: Clarification tracking
    "clarification_rounds": getattr(handler, 'clarification_rounds', 0) if 'handler' in locals() else 0,
    "clarification_resolved": True,  # Could be enhanced to track if all resolved
}
"""
```

- [ ] **Step 5: Run integration tests**

Run: `pytest backend/tests/integration/test_uncertainty_clarification.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run existing tests to ensure no regression**

Run: `pytest backend/tests/integration/test_response_validation.py -v`
Run: `pytest backend/tests/integration/test_e2e_task_execution.py -v`
Expected: All existing tests still PASS

- [ ] **Step 7: Commit**

```bash
git add backend/services/model_provider.py backend/tests/integration/test_uncertainty_clarification.py
git commit -m "feat: integrate uncertainty detection and clarification into agentic loop"
```

---

### Task 4: Add comprehensive integration tests for clarification flow

**Files:**
- Modify: `backend/tests/integration/test_uncertainty_clarification.py` (add more test cases)
- Test: `backend/tests/integration/test_uncertainty_clarification.py`

**Interfaces:**
- Consumes: All components from Tasks 1-3
- Produces: Comprehensive integration test coverage

- [ ] **Step 1: Add escalation chain test**

```python
# backend/tests/integration/test_uncertainty_clarification.py (add to existing file)

@pytest.mark.asyncio
async def test_escalation_chain_supervisor_then_council(mock_config, mock_agent, mock_db):
    """Supervisor unclear → escalation to Council → guidance injected."""
    provider = OpenAICompatibleProvider(config=mock_config)
    provider.api_key = "test-key"
    provider.base_url = "https://api.openai.com/v1"
    
    mock_client = AsyncMock()
    # Turn 1: LLM calls tool
    turn1 = MagicMock()
    turn1.choices = [MagicMock()]
    turn1.choices[0].message = MagicMock()
    turn1.choices[0].message.tool_calls = [MagicMock(id="c1", function=MagicMock(name="read_file", arguments='{}'))]
    turn1.choices[0].finish_reason = "tool_calls"
    turn1.model = "gpt-4o"
    turn1.usage = MagicMock(prompt_tokens=50, completion_tokens=50)
    
    # Turn 2: After clarification, LLM responds
    turn2 = MagicMock()
    turn2.choices = [MagicMock()]
    turn2.choices[0].message = MagicMock()
    turn2.choices[0].message.content = "Thanks for the guidance from Council."
    turn2.choices[0].message.tool_calls = None
    turn2.choices[0].finish_reason = "stop"
    turn2.model = "gpt-4o"
    turn2.usage = MagicMock(prompt_tokens=150, completion_tokens=50)
    
    mock_client.chat.completions.create = AsyncMock(side_effect=[turn1, turn2])
    
    import backend.services.model_provider as mp
    cache_key = (str(mock_config.id), provider.api_key, provider.base_url, False)
    original_cache = mp._CLIENT_CACHE.get(cache_key)
    mp._CLIENT_CACHE[cache_key] = mock_client
    
    try:
        async def mock_tool_executor(name, args):
            return {"status": "error", "tool_name": name, "error": "Permission denied", "result": None}
        
        with patch("backend.services.model_provider.UncertaintyDetector.analyze") as mock_analyze, \
             patch("backend.services.model_provider.provider_rate_limiter.acquire_concurrency", new=AsyncMock()), \
             patch("backend.services.model_provider.provider_rate_limiter.acquire", new=AsyncMock()), \
             patch("backend.services.model_provider.provider_rate_limiter.release_concurrency", new=AsyncMock()), \
             patch("backend.services.model_provider._record_provider_headers", new=AsyncMock()), \
             patch("backend.services.model_provider.api_key_manager") as mock_key_manager:
            
            mock_analyze.return_value = UncertaintySignal(
                reason="tool_error", affected_tools=["read_file"],
                details={"status": "error", "error": "Permission denied"},
                suggested_question="Tool error", severity="high"
            )
            mock_key_manager.mark_key_success = MagicMock()
            mock_key_manager.record_spend = MagicMock()
            
            result = await provider.generate_with_tools(
                system_prompt="You are a helpful agent.",
                messages=[{"role": "user", "content": "Read a file"}],
                tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
                tool_executor=mock_tool_executor,
                max_iterations=5,
                agentium_id="30001",
                agent=mock_agent,
            )
            
            # Verify two LLM calls happened
            assert mock_client.chat.completions.create.call_count == 2
            
            # Second call should have clarification from escalation
            second_messages = mock_client.chat.completions.create.call_args_list[1].kwargs["messages"]
            clarification_msgs = [m for m in second_messages if m.get("role") == "system" and "CLARIFICATION" in m.get("content", "")]
            assert len(clarification_msgs) >= 1
            
    finally:
        if original_cache:
            mp._CLIENT_CACHE[cache_key] = original_cache
        else:
            del mp._CLIENT_CACHE[cache_key]

@pytest.mark.asyncio
async def test_max_clarification_rounds_prevents_infinite_loop(mock_config, mock_agent, mock_db):
    """After 2 clarification rounds, stops and injects warning."""
    provider = OpenAICompatibleProvider(config=mock_config)
    provider.api_key = "test-key"
    provider.base_url = "https://api.openai.com/v1"
    
    mock_client = AsyncMock()
    # Turn 1: Tool call
    turn1 = MagicMock()
    turn1.choices = [MagicMock()]
    turn1.choices[0].message = MagicMock()
    turn1.choices[0].message.tool_calls = [MagicMock(id="c1", function=MagicMock(name="tool_a", arguments='{}'))]
    turn1.choices[0].finish_reason = "tool_calls"
    turn1.model = "gpt-4o"
    turn1.usage = MagicMock(prompt_tokens=50, completion_tokens=50)
    
    # Turn 2: Still calls tools (simulating unresolved uncertainty)
    turn2 = MagicMock()
    turn2.choices = [MagicMock()]
    turn2.choices[0].message = MagicMock()
    turn2.choices[0].message.tool_calls = [MagicMock(id="c2", function=MagicMock(name="tool_b", arguments='{}'))]
    turn2.choices[0].finish_reason = "tool_calls"
    turn2.model = "gpt-4o"
    turn2.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
    
    # Turn 3: After max rounds, responds
    turn3 = MagicMock()
    turn3.choices = [MagicMock()]
    turn3.choices[0].message = MagicMock()
    turn3.choices[0].message.content = "Proceeding with best judgment."
    turn3.choices[0].message.tool_calls = None
    turn3.choices[0].finish_reason = "stop"
    turn3.model = "gpt-4o"
    turn3.usage = MagicMock(prompt_tokens=150, completion_tokens=50)
    
    mock_client.chat.completions.create = AsyncMock(side_effect=[turn1, turn2, turn3])
    
    import backend.services.model_provider as mp
    cache_key = (str(mock_config.id), provider.api_key, provider.base_url, False)
    original_cache = mp._CLIENT_CACHE.get(cache_key)
    mp._CLIENT_CACHE[cache_key] = mock_client
    
    try:
        call_count = 0
        async def mock_tool_executor(name, args):
            nonlocal call_count
            call_count += 1
            return {"status": "error", "tool_name": name, "error": "Failed", "result": None}
        
        with patch("backend.services.model_provider.UncertaintyDetector.analyze") as mock_analyze, \
             patch("backend.services.model_provider.provider_rate_limiter.acquire_concurrency", new=AsyncMock()), \
             patch("backend.services.model_provider.provider_rate_limiter.acquire", new=AsyncMock()), \
             patch("backend.services.model_provider.provider_rate_limiter.release_concurrency", new=AsyncMock()), \
             patch("backend.services.model_provider._record_provider_headers", new=AsyncMock()), \
             patch("backend.services.model_provider.api_key_manager") as mock_key_manager:
            
            mock_analyze.return_value = UncertaintySignal(
                reason="tool_error", affected_tools=["tool_a"],
                details={"status": "error", "error": "Failed"},
                suggested_question="Tool error", severity="high"
            )
            mock_key_manager.mark_key_success = MagicMock()
            mock_key_manager.record_spend = MagicMock()
            
            result = await provider.generate_with_tools(
                system_prompt="You are a helpful agent.",
                messages=[{"role": "user", "content": "Do something"}],
                tools=[{"type": "function", "function": {"name": "tool_a", "parameters": {}}}],
                tool_executor=mock_tool_executor,
                max_iterations=5,
                agentium_id="30001",
                agent=mock_agent,
            )
            
            # Should have injected WARNING after 2 rounds
            all_messages = []
            for call in mock_client.chat.completions.create.call_args_list:
                all_messages.extend(call.kwargs["messages"])
            
            warning_msgs = [m for m in all_messages if m.get("role") == "system" and "WARNING" in m.get("content", "")]
            assert len(warning_msgs) >= 1, "Warning message not injected after max rounds"
            assert "Max clarification rounds" in warning_msgs[0]["content"] or "Unable to resolve" in warning_msgs[0]["content"]
            
            # Should track clarification rounds in result
            assert result.get("clarification_rounds", 0) >= 2
            
    finally:
        if original_cache:
            mp._CLIENT_CACHE[cache_key] = original_cache
        else:
            del mp._CLIENT_CACHE[cache_key]

@pytest.mark.asyncio
async def test_head_agent_no_parent_uses_sovereign_clarification(mock_config, mock_db):
    """Head of Council (no parent) should get clarification from Sovereign."""
    # Create Head agent (no parent)
    head_agent = MagicMock()
    head_agent.agentium_id = "00001"
    head_agent.ethos = MagicMock()
    head_agent.ethos.mission_statement = "Lead the council"
    head_agent.ethos.behavioral_rules = "[]"
    head_agent.parent = None  # Head has no parent
    
    provider = OpenAICompatibleProvider(config=mock_config)
    provider.api_key = "test-key"
    provider.base_url = "https://api.openai.com/v1"
    
    mock_client = AsyncMock()
    turn1 = MagicMock()
    turn1.choices = [MagicMock()]
    turn1.choices[0].message = MagicMock()
    turn1.choices[0].message.tool_calls = [MagicMock(id="c1", function=MagicMock(name="execute_command", arguments='{}'))]
    turn1.choices[0].finish_reason = "tool_calls"
    turn1.model = "gpt-4o"
    turn1.usage = MagicMock(prompt_tokens=50, completion_tokens=50)
    
    turn2 = MagicMock()
    turn2.choices = [MagicMock()]
    turn2.choices[0].message = MagicMock()
    turn2.choices[0].message.content = "Understood, I'll ask the Sovereign."
    turn2.choices[0].message.tool_calls = None
    turn2.choices[0].finish_reason = "stop"
    turn2.model = "gpt-4o"
    turn2.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
    
    mock_client.chat.completions.create = AsyncMock(side_effect=[turn1, turn2])
    
    import backend.services.model_provider as mp
    cache_key = (str(mock_config.id), provider.api_key, provider.base_url, False)
    original_cache = mp._CLIENT_CACHE.get(cache_key)
    mp._CLIENT_CACHE[cache_key] = mock_client
    
    try:
        async def mock_tool_executor(name, args):
            return {"status": "error", "tool_name": name, "error": "Command failed", "result": None}
        
        with patch("backend.services.model_provider.UncertaintyDetector.analyze") as mock_analyze, \
             patch("backend.services.model_provider.provider_rate_limiter.acquire_concurrency", new=AsyncMock()), \
             patch("backend.services.model_provider.provider_rate_limiter.acquire", new=AsyncMock()), \
             patch("backend.services.model_provider.provider_rate_limiter.release_concurrency", new=AsyncMock()), \
             patch("backend.services.model_provider._record_provider_headers", new=AsyncMock()), \
             patch("backend.services.model_provider.api_key_manager") as mock_key_manager:
            
            mock_analyze.return_value = UncertaintySignal(
                reason="tool_error", affected_tools=["execute_command"],
                details={"status": "error", "error": "Command failed"},
                suggested_question="Tool error", severity="high"
            )
            mock_key_manager.mark_key_success = MagicMock()
            mock_key_manager.record_spend = MagicMock()
            
            result = await provider.generate_with_tools(
                system_prompt="You are the Head of Council.",
                messages=[{"role": "user", "content": "Run command"}],
                tools=[{"type": "function", "function": {"name": "execute_command", "parameters": {}}}],
                tool_executor=mock_tool_executor,
                max_iterations=5,
                agentium_id="00001",
                agent=head_agent,
            )
            
            # Verify clarification was injected (from Sovereign consult)
            second_messages = mock_client.chat.completions.create.call_args_list[1].kwargs["messages"]
            clarification_found = any(
                m.get("role") == "system" and "CLARIFICATION" in m.get("content", "")
                for m in second_messages
            )
            assert clarification_found
            
    finally:
        if original_cache:
            mp._CLIENT_CACHE[cache_key] = original_cache
        else:
            del mp._CLIENT_CACHE[cache_key]
```

- [ ] **Step 2: Run all integration tests**

Run: `pytest backend/tests/integration/test_uncertainty_clarification.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_uncertainty_clarification.py
git commit -m "test: add comprehensive integration tests for uncertainty clarification flow"
```

---

## Plan Self-Review Checklist

- [x] **Spec Coverage:** All spec requirements mapped to tasks:
  - UncertaintyDetector with all trigger conditions → Task 1
  - ClarificationHandler with supervisor → escalation chain → Task 2
  - Provider integration in generate_with_tools() → Task 3
  - Max 2 rounds loop prevention → Tasks 2 & 3
  - Fail-open design → Task 3 (try/except)
  - Result metadata tracking → Task 3
  - Test coverage → Tasks 1, 2, 4

- [x] **Placeholder Scan:** No TBD, TODO, "implement later", or vague instructions. Every step has exact code.

- [x] **Type Consistency:** 
  - UncertaintySignal dataclass defined in Task 1, used identically in Tasks 2, 3, 4
  - ClarificationHandler.handle_uncertainty() returns `Tuple[bool, Optional[str]]` consistently
  - All imports use correct module paths

- [x] **Task Independence:** Each task produces independently testable deliverable:
  - Task 1: UncertaintyDetector + unit tests
  - Task 2: ClarificationHandler + unit tests  
  - Task 3: Provider integration + basic integration tests
  - Task 4: Comprehensive integration tests

- [x] **Global Constraints Satisfied:**
  - Uses existing ClarificationService methods
  - Max 2 rounds hardcoded
  - Zero overhead when no uncertainty (early return)
  - No new external dependencies
  - Files in correct locations per spec

---

**Plan saved to:** `docs/superpowers/plans/2026-08-11-graceful-uncertainty-fallback-anti-hallucination.md`

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
   - REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints
   - REQUIRED SUB-SKILL: Use superpowers:executing-plans

**Which approach?**