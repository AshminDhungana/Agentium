import pytest
from backend.services import chat_service as cs
from backend.services.decision_engine import DecisionAction


def _result_with_decide(action="create_task", task_brief="Build a scraper", rationale="build", confidence=0.9):
    """Build a result dict shaped like provider.generate_with_tools output.

    The top-level dict has NO `tool_calls` key; parsed tool calls live only
    inside result["messages"][*].tool_calls (the assistant turns).
    """
    return {
        "content": "On it, Sovereign.",
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "Build me a scraper"},
            {
                "role": "assistant",
                "content": "On it, Sovereign.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "decide",
                            "arguments": (
                                f'{{"action": "{action}", "rationale": "{rationale}", '
                                f'"task_brief": "{task_brief}", "confidence": {confidence}}}'
                            ),
                        },
                    }
                ],
            },
        ],
    }


def test_classify_action_from_result_reads_decide_from_messages():
    result = _result_with_decide()
    decision = cs.ChatService.classify_action_from_result(result)
    assert decision.action is DecisionAction.CREATE_TASK
    assert decision.task_brief == "Build a scraper"


def test_classify_action_from_result_ignores_non_assistant_and_other_tools():
    # tool_calls in a user turn, plus an assistant turn without decide -> REPLY
    result = {
        "messages": [
            {
                "role": "user",
                "tool_calls": [
                    {"function": {"name": "decide", "arguments": '{"action": "create_task"}'}}
                ],
            },
            {
                "role": "assistant",
                "content": "hi",
                "tool_calls": [
                    {"function": {"name": "web_search", "arguments": "{}"}}
                ],
            },
        ]
    }
    decision = cs.ChatService.classify_action_from_result(result)
    assert decision.action is DecisionAction.REPLY


def test_classify_action_from_result_defaults_to_reply():
    decision = cs.ChatService.classify_action_from_result({"messages": []})
    assert decision.action is DecisionAction.REPLY
