"""
Tests for the Genesis welcome message: it must be persisted to chat history
as a head_of_council message AND broadcast as a `message`-type event (not
`genesis_prompt`).
"""
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from backend.services import initialization_service as init_svc


@pytest.fixture
def svc_with_sovereign():
    """An InitializationService whose DB returns a sovereign user and records adds."""
    svc = init_svc.InitializationService(db=MagicMock())
    user = MagicMock()
    user.id = 1
    svc.db.query.return_value.filter_by.return_value.first.return_value = user
    return svc


async def test_notify_persists_head_message(svc_with_sovereign):
    from backend.models.entities.chat_message import ChatMessage as ChatMsg

    svc = svc_with_sovereign
    await svc._notify_country_name_decision("Veridia", user_provided=True)

    # Exactly one ChatMessage was added, and it is a head_of_council welcome.
    assert svc.db.add.call_count == 1
    added = svc.db.add.call_args.args[0]
    assert isinstance(added, ChatMsg)
    assert added.role == "head_of_council"
    assert "Veridia" in added.content
    assert "Welcome" in added.content


async def test_notify_broadcasts_message_type(svc_with_sovereign):
    svc = svc_with_sovereign
    with patch(
        "backend.api.routes.websocket.manager.broadcast",
        new=AsyncMock(),
    ) as broadcast:
        await svc._notify_country_name_decision("Veridia", user_provided=True)

    assert broadcast.call_count == 1
    payload = broadcast.call_args.args[0]
    assert payload["type"] == "message"
    assert payload["role"] == "head_of_council"
    assert "Veridia" in payload["content"]
    assert payload["message_id"]  # stable id for client dedup


async def test_notify_default_name_when_not_provided(svc_with_sovereign):
    from backend.models.entities.chat_message import ChatMessage as ChatMsg

    svc = svc_with_sovereign
    with patch(
        "backend.api.routes.websocket.manager.broadcast",
        new=AsyncMock(),
    ):
        await svc._notify_country_name_decision(
            "The Agentium Sovereignty", user_provided=False
        )

    added = svc.db.add.call_args.args[0]
    assert isinstance(added, ChatMsg)
    assert added.role == "head_of_council"
    assert "The Agentium Sovereignty" in added.content
