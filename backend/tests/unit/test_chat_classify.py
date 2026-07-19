import pytest
from backend.services import chat_service as cs
from backend.services.decision_engine import DecisionAction


def test_classify_action_from_result_reads_decide_tool():
    result = {
        "tool_calls": [
            {
                "function": {
                    "name": "decide",
                    "arguments": '{"action": "create_task", "rationale": "build", '
                                 '"task_brief": "Build a scraper", "confidence": 0.9}',
                }
            }
        ]
    }
    decision = cs.ChatService.classify_action_from_result(result)
    assert decision.action is DecisionAction.CREATE_TASK
    assert decision.task_brief == "Build a scraper"


def test_classify_action_from_result_defaults_to_reply():
    decision = cs.ChatService.classify_action_from_result({"tool_calls": []})
    assert decision.action is DecisionAction.REPLY
