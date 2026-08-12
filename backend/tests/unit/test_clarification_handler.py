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