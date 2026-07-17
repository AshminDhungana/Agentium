import pytest
from backend.services.decision_engine import Decision, DecisionAction


class _FakeAgent:
    id = "00001"
    agentium_id = "00001"
    agent_tier = "0xxxx"
    preferred_config_id = None


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
    from backend.services.decision_engine import DecisionEngine
    engine = DecisionEngine()
    fake_llm = _make_fake_llm("create_task")
    decision = await engine.decide(
        agent=_FakeAgent(), message="build me a scraper", db=None, _llm=fake_llm
    )
    assert decision.action is DecisionAction.CREATE_TASK
    assert decision.confidence == 0.9


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


@pytest.mark.asyncio
async def test_analyze_for_task_uses_engine(monkeypatch):
    from backend.services import chat_service
    from backend.services.decision_engine import Decision, DecisionAction

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
