import pytest
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.constitution import Constitution, Ethos
from backend.models.entities.voting import AmendmentVoting, TaskDeliberation, IndividualVote, VotingRecord


def test_governance_fixtures_compile():
    """Verify all governance fixtures can be imported without error."""
    from backend.tests.unit.models.conftest import (
        sample_head_of_council,
        sample_council_member,
        sample_lead_agent,
        sample_task_agent,
        sample_constitution,
        sample_ethos,
        sample_amendment_voting,
        sample_task_deliberation,
    )
    assert sample_head_of_council is not None
    assert sample_council_member is not None
    assert sample_lead_agent is not None
    assert sample_task_agent is not None
    assert sample_constitution is not None
    assert sample_ethos is not None
    assert sample_amendment_voting is not None
    assert sample_task_deliberation is not None