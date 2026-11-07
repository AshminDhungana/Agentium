"""Tests for seed_db.py genesis agent creation."""
import os
import pytest
from sqlalchemy.orm import Session

# Set TESTING before importing seed_db
os.environ["TESTING"] = "true"

from backend.tests.load.seed_db import create_genesis_agents
from backend.models.entities.agents import HeadOfCouncil, CouncilMember, LeadAgent


@pytest.mark.asyncio
async def test_create_genesis_agents_creates_all_agents(db_session: Session):
    """Test that create_genesis_agents creates Head, Council, and Lead."""
    result = await create_genesis_agents(db_session)

    # Verify return structure
    assert result["head"] is not None
    assert len(result["council"]) == 2
    assert result["lead"] is not None

    # Verify Head 00001
    head = db_session.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    assert head is not None
    assert head.name == "Head of Council Prime"
    assert head.is_active is True
    assert head.is_persistent is True
    assert head.ethos_id is not None

    # Verify Council 10001, 10002
    council = db_session.query(CouncilMember).filter(
        CouncilMember.agentium_id.in_(["10001", "10002"])
    ).all()
    assert len(council) == 2
    for member in council:
        assert member.is_active is True
        assert member.parent_id == head.id
        assert member.ethos_id is not None

    # Verify Lead 20001
    lead = db_session.query(LeadAgent).filter_by(agentium_id="20001").first()
    assert lead is not None
    assert lead.is_active is True
    assert lead.parent_id == head.id


@pytest.mark.asyncio
async def test_create_genesis_agents_idempotent(db_session: Session):
    """Test that running create_genesis_agents twice doesn't duplicate."""
    await create_genesis_agents(db_session)
    result2 = await create_genesis_agents(db_session)

    # Should return same objects, not create duplicates
    assert result2["head"].id == result2["head"].id
    assert len(result2["council"]) == 2

    # Verify DB has exactly one of each
    head_count = db_session.query(HeadOfCouncil).filter_by(agentium_id="00001").count()
    council_count = db_session.query(CouncilMember).filter(
        CouncilMember.agentium_id.in_(["10001", "10002"])
    ).count()
    lead_count = db_session.query(LeadAgent).filter_by(agentium_id="20001").count()

    assert head_count == 1
    assert council_count == 2
    assert lead_count == 1