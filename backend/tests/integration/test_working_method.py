"""Integration tests for 6.3 — default Ethos working procedure + capabilities."""
import pytest

from sqlalchemy.orm import Session

from backend.tools.ethos_tool import ethos_tool
from backend.models.entities.agents import CouncilMember
from backend.services.reincarnation_service import reincarnation_service

pytestmark = pytest.mark.integration


async def test_spawned_agent_ethos_has_working_method_and_capabilities(seeded_db: Session):
    """6.3 acceptance: a fresh agent's Ethos, inspected directly, includes both
    its working procedure (working_method) and its capabilities."""
    parent = seeded_db.query(CouncilMember).first()
    assert parent is not None

    task_agent = reincarnation_service.spawn_task_agent(
        parent=parent,
        name="Procedure Probe",
        description="End-to-end acceptance probe for Ethos working method",
        db=seeded_db,
    )
    seeded_db.commit()

    result = await ethos_tool.execute(
        action="read",
        db=seeded_db,
        agent_id=task_agent.agentium_id,
    )
    assert result["success"] is True

    data = result["data"]
    assert data["working_method"], "fresh Ethos must include a working procedure"
    assert "consult the knowledge base" in data["working_method"].lower()
    assert isinstance(data["capabilities"], list)
    assert len(data["capabilities"]) > 0
    # 6.1 grounding must remain intact alongside the new field.
    assert data["environment_context"]
