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
