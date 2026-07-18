# backend/tests/unit/test_clarification_tool.py
import asyncio
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from backend.services.chat_service import ChatService
from backend.models.schemas.structured_input import StructuredInputCard, CardQuestion, CardOption


def test_send_structured_card_persists_and_broadcasts():
    card = StructuredInputCard(
        card_id="card-unit-1",
        title="Pick one",
        questions=[CardQuestion(
            id="q1", question="Color?", input_type="single_select", required=True,
            options=[CardOption(id="a", label="Red", value="red")],
        )],
    )
    db = MagicMock(spec=Session)
    saved = {}
    def add(m):
        saved["msg"] = m
    db.add.side_effect = add

    with patch("backend.services.chat_service.ws_manager") as ws, \
         patch("backend.services.chat_service.ChatMessageEntity") as Msg:
        Msg.return_value = MagicMock()
        Msg.return_value.to_dict.return_value = {"id": "m1", "card_id": "card-unit-1"}
        result = ChatService.send_structured_card(card, db, "user-1")

    db.add.assert_called_once()
    db.commit.assert_called_once()
    assert result["id"] == "m1"
    # broadcast scheduled as a task on the running loop
    assert ws.broadcast.called
    broadcast_msg = ws.broadcast.call_args.args[0]
    assert broadcast_msg["type"] == "message"
    assert broadcast_msg["metadata"]["card"]["card_id"] == "card-unit-1"


from backend.tools.clarification_tool import request_user_clarification


def test_request_user_clarification_tool_happy_path():
    card = {}
    with patch("backend.tools.clarification_tool.ChatService") as CS, \
         patch("backend.tools.clarification_tool._resolve_sovereign_user_id", return_value="u1"):
        CS.send_structured_card.return_value = {"card_id": "card-x", "id": "m9"}
        out = request_user_clarification(
            title="T", questions=[{
                "id": "q1", "question": "Q?", "input_type": "single_select",
                "required": True, "options": [{"id": "a", "label": "A", "value": "a"}],
            }], db=MagicMock(),
        )
    assert out.startswith("ok:"), out
    assert "card-x" in out


def test_request_user_clarification_tool_rejects_empty():
    out = request_user_clarification(questions=[], db=MagicMock())
    assert out.startswith("error:")


def test_request_user_clarification_tool_send_failure():
    with patch("backend.tools.clarification_tool.ChatService") as CS, \
         patch("backend.tools.clarification_tool._resolve_sovereign_user_id", return_value="u1"):
        CS.send_structured_card.side_effect = RuntimeError("boom")
        out = request_user_clarification(
            title="T", questions=[{
                "id": "q1", "question": "Q?", "input_type": "single_select",
                "required": True, "options": [{"id": "a", "label": "A", "value": "a"}],
            }], db=MagicMock(),
        )
    assert out.startswith("error:")
    assert "failed to send" in out


def test_request_user_clarification_tool_no_sovereign():
    with patch("backend.tools.clarification_tool.ChatService") as CS, \
         patch("backend.tools.clarification_tool._resolve_sovereign_user_id", return_value=""):
        out = request_user_clarification(
            title="T", questions=[{
                "id": "q1", "question": "Q?", "input_type": "single_select",
                "required": True, "options": [{"id": "a", "label": "A", "value": "a"}],
            }], db=MagicMock(),
        )
    assert out == "error: no sovereign user found"
    CS.send_structured_card.assert_not_called()
