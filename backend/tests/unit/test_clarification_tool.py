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
