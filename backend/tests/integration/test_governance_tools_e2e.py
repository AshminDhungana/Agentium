import pytest
from backend.core.tool_registry import tool_registry
from backend.models.entities.agents import Agent, HeadOfCouncil, LeadAgent


@pytest.mark.integration
def test_head_spawns_task_agent(seeded_db):
    db = seeded_db
    fn = tool_registry.get_tool_function("spawn_agent")
    res = fn(agent_type="task", name="Worker", description="does work",
             db=db, agent_id="00001")
    assert res["success"] is True
    assert res["data"]["agent_type"] == "task_agent"


@pytest.mark.integration
def test_head_create_dispatch_complete_task(seeded_db):
    db = seeded_db
    lead = db.query(LeadAgent).filter(LeadAgent.status == "active").first()
    assert lead is not None, "test requires a seeded active Lead"
    ct = tool_registry.get_tool_function("create_task")
    c_res = ct(title="T", description="D", db=db, agent_id="00001")
    assert c_res["success"] is True
    task_id = c_res["data"]["task_id"]

    dt = tool_registry.get_tool_function("dispatch_task")
    d_res = dt(task_id=task_id, target_agentium_id=lead.agentium_id, db=db, agent_id="00001")
    assert d_res["success"] is True

    cm = tool_registry.get_tool_function("complete_task")
    m_res = cm(task_id=task_id, result_summary="done", db=db, agent_id="00001")
    assert m_res["success"] is True
    assert m_res["data"]["status"] == "completed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_head_full_vote_cycle(seeded_db):
    db = seeded_db
    pa = tool_registry.get_tool_function("propose_amendment")
    p_res = await pa(title="Amend A", description="reason", proposed_text="diff", db=db, agent_id="00001")
    assert p_res["success"] is True
    aid = p_res["data"]["amendment_id"]

    ov = tool_registry.get_tool_function("open_vote")
    assert (await ov(amendment_id=aid, db=db, agent_id="00001"))["success"] is True

    cv = tool_registry.get_tool_function("cast_vote")
    council = db.query(Agent).filter(Agent.agentium_id.like("1%")).all()
    for c in council:
        r = await cv(amendment_id=aid, vote="for", db=db, agent_id=c.agentium_id)
        assert r["success"] is True

    cl = tool_registry.get_tool_function("conclude_vote")
    cl_res = await cl(amendment_id=aid, db=db, agent_id="00001")
    assert cl_res["success"] is True
