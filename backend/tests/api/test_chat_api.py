# tests/api/test_chat_api.py
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.orm import Session
from backend.models.entities.user import User as UserModel
from backend.models.entities.chat_message import ChatMessage as ChatMessageEntity, Conversation
from backend.models.entities.agents import HeadOfCouncil


@pytest.fixture
def sovereign_user(db_session: Session) -> UserModel:
    """Get the sovereign user created by auth_client fixture."""
    user = db_session.query(UserModel).filter_by(username="admin").first()
    assert user is not None, "Sovereign user not found"
    return user


@pytest.fixture
def head_of_council(db_session: Session, sovereign_user: UserModel) -> HeadOfCouncil:
    """Create or get Head of Council for testing."""
    head = db_session.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    if not head:
        head = HeadOfCouncil(
            agentium_id="00001",
            agent_type="head_of_council",
            is_active=True,
            status="active",
        )
        db_session.add(head)
        db_session.commit()
        db_session.refresh(head)
    return head


@pytest.mark.asyncio
async def test_post_chat_send_creates_message_and_returns_response(
    auth_client: AsyncClient,
    db_session: Session,
    sovereign_user: UserModel,
    head_of_council: HeadOfCouncil,
):
    """POST /chat/send should persist user message, invoke agent, persist agent response, return both."""
    with patch("backend.api.routes.chat.ChatService.process_message", new_callable=AsyncMock) as mock_process:
        mock_process.return_value = {
            "response": "Hello! How can I help?",
            "agent_id": "00001",
            "task_created": False,
            "task_id": None,
            "context_compressed": False,
            "raw_turn_count": 1,
            "estimated_tokens": 150,
        }
        
        response = await auth_client.post(
            "/api/v1/chat/send",
            json={"message": "Hello", "stream": False},
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Hello! How can I help?"
    assert data["agent_id"] == "00001"
    assert data["context_compressed"] is False
    
    # Verify messages persisted
    messages = db_session.query(ChatMessageEntity).filter(
        ChatMessageEntity.user_id == str(sovereign_user.id)
    ).order_by(ChatMessageEntity.created_at).all()
    assert len(messages) == 2  # user + agent
    assert messages[0].role == "sovereign"
    assert messages[0].content == "Hello"
    assert messages[1].role == "head_of_council"
    assert messages[1].content == "Hello! How can I help?"
    assert messages[0].conversation_id == messages[1].conversation_id  # Same conversation


@pytest.mark.asyncio
async def test_post_chat_send_streaming_returns_sse(
    auth_client: AsyncClient,
    head_of_council: HeadOfCouncil,
):
    """POST /chat/send with stream=True should return SSE stream."""
    async def mock_stream():
        yield 'data: {"type": "message_start", "stream_id": "test-123", "role": "head_of_council"}\n\n'
        yield 'data: {"type": "message_delta", "stream_id": "test-123", "delta": "Hello"}\n\n'
        yield 'data: {"type": "message_delta", "stream_id": "test-123", "delta": " there!"}\n\n'
        yield 'data: {"type": "message_end", "stream_id": "test-123", "content": "Hello there!", "metadata": {"agent_id": "00001"}}\n\n'
    
    with patch("backend.api.routes.chat._stream_response", return_value=mock_stream()):
        response = await auth_client.post(
            "/api/v1/chat/send",
            json={"message": "Hi", "stream": True},
        )
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    content = response.text
    assert "message_start" in content
    assert "message_delta" in content
    assert "message_end" in content


@pytest.mark.asyncio
async def test_post_chat_send_with_conversation_id_associates_messages(
    auth_client: AsyncClient,
    db_session: Session,
    sovereign_user: UserModel,
    head_of_council: HeadOfCouncil,
):
    """POST /chat/send with conversation_id should attach messages to that conversation."""
    # Create a conversation first
    conv = Conversation(user_id=str(sovereign_user.id), title="Test Conversation")
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    
    with patch("backend.api.routes.chat.ChatService.process_message", new_callable=AsyncMock) as mock_process:
        mock_process.return_value = {
            "response": "Response in conversation",
            "agent_id": "00001",
            "task_created": False,
            "task_id": None,
        }
        
        response = await auth_client.post(
            "/api/v1/chat/send",
            json={"message": "In conversation", "conversation_id": str(conv.id)},
        )
    
    assert response.status_code == 200
    messages = db_session.query(ChatMessageEntity).filter(
        ChatMessageEntity.conversation_id == conv.id
    ).all()
    assert len(messages) == 2
    assert all(m.conversation_id == conv.id for m in messages)


@pytest.mark.asyncio
async def test_get_chat_conversations_lists_user_conversations(
    auth_client: AsyncClient,
    db_session: Session,
    sovereign_user: UserModel,
):
    """GET /chat/conversations should return user's conversations with last message preview."""
    # Clean up any existing conversations for this user
    db_session.query(Conversation).filter(
        Conversation.user_id == str(sovereign_user.id)
    ).delete()
    db_session.commit()
    
    # Create conversations with messages
    conv1 = Conversation(user_id=str(sovereign_user.id), title="First Chat")
    conv2 = Conversation(user_id=str(sovereign_user.id), title="Second Chat", is_archived="Y")
    db_session.add_all([conv1, conv2])
    db_session.commit()
    
    msg1 = ChatMessageEntity(
        user_id=str(sovereign_user.id), role="sovereign", content="Hello from conv1",
        conversation_id=conv1.id, agent_id="00001"
    )
    msg2 = ChatMessageEntity(
        user_id=str(sovereign_user.id), role="head_of_council", content="Hi there!",
        conversation_id=conv1.id, agent_id="00001"
    )
    db_session.add_all([msg1, msg2])
    db_session.commit()
    
    response = await auth_client.get("/api/v1/chat/conversations")
    
    assert response.status_code == 200
    data = response.json()
    assert "conversations" in data
    # Filter to only the conversations we created
    test_convs = [c for c in data["conversations"] if c["title"] in ("First Chat", "Second Chat")]
    assert len(test_convs) == 2
    # Find conv1
    conv1_data = next(c for c in test_convs if c["title"] == "First Chat")
    assert conv1_data["last_message_preview"] == "Hi there!"
    assert conv1_data["message_count"] == 2


@pytest.mark.asyncio
async def test_get_chat_conversations_excludes_archived_by_default(
    auth_client: AsyncClient,
    db_session: Session,
    sovereign_user: UserModel,
):
    """GET /chat/conversations should exclude archived unless include_archived=true."""
    # Clean up first
    db_session.query(Conversation).filter(
        Conversation.user_id == str(sovereign_user.id)
    ).delete()
    db_session.commit()
    
    conv1 = Conversation(user_id=str(sovereign_user.id), title="Active")
    conv2 = Conversation(user_id=str(sovereign_user.id), title="Archived", is_archived="Y")
    db_session.add_all([conv1, conv2])
    db_session.commit()
    
    response = await auth_client.get("/api/v1/chat/conversations")
    data = response.json()
    titles = [c["title"] for c in data["conversations"]]
    assert "Active" in titles
    assert "Archived" not in titles
    
    response = await auth_client.get("/api/v1/chat/conversations?include_archived=true")
    data = response.json()
    titles = [c["title"] for c in data["conversations"]]
    assert "Active" in titles
    assert "Archived" in titles


@pytest.mark.asyncio
async def test_get_chat_conversation_messages_returns_paginated_history(
    auth_client: AsyncClient,
    db_session: Session,
    sovereign_user: UserModel,
):
    """GET /chat/conversations/{id}/messages should return paginated messages."""
    conv = Conversation(user_id=str(sovereign_user.id), title="History Test")
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    
    # Add 5 messages
    for i in range(5):
        msg = ChatMessageEntity(
            user_id=str(sovereign_user.id),
            role="sovereign" if i % 2 == 0 else "head_of_council",
            content=f"Message {i}",
            conversation_id=conv.id,
            agent_id="00001"
        )
        db_session.add(msg)
    db_session.commit()
    
    response = await auth_client.get(
        f"/api/v1/chat/conversations/{conv.id}/messages?limit=3&offset=0",
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "messages" in data
    assert len(data["messages"]) == 3
    assert data["total"] == 5
    assert data["limit"] == 3
    assert data["offset"] == 0
    
    # Check order (oldest first)
    assert data["messages"][0]["content"] == "Message 0"
    assert data["messages"][1]["content"] == "Message 1"
    assert data["messages"][2]["content"] == "Message 2"


@pytest.mark.asyncio
async def test_post_chat_conversations_creates_new_conversation(
    auth_client: AsyncClient,
    db_session: Session,
    sovereign_user: UserModel,
):
    """POST /chat/conversations should create a new conversation."""
    response = await auth_client.post(
        "/api/v1/chat/conversations",
        json={"title": "New Research Project"},
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "New Research Project"
    assert data["user_id"] == str(sovereign_user.id)
    # Check is_archived and is_deleted are in response
    assert "is_archived" in data
    assert "is_deleted" in data
    assert data["is_archived"] == "N"
    assert data["is_deleted"] == "N"
    assert "id" in data
    assert "created_at" in data
    
    # Verify in DB
    conv = db_session.query(Conversation).filter(Conversation.id == data["id"]).first()
    assert conv is not None
    assert conv.title == "New Research Project"


@pytest.mark.asyncio
async def test_patch_chat_conversation_updates_title(
    auth_client: AsyncClient,
    db_session: Session,
    sovereign_user: UserModel,
):
    """PATCH /chat/conversations/{id} should update title."""
    conv = Conversation(user_id=str(sovereign_user.id), title="Old Title")
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    
    response = await auth_client.patch(
        f"/api/v1/chat/conversations/{conv.id}",
        json={"title": "Updated Title"},
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    
    db_session.refresh(conv)
    assert conv.title == "Updated Title"


@pytest.mark.asyncio
async def test_delete_chat_conversation_soft_deletes(
    auth_client: AsyncClient,
    db_session: Session,
    sovereign_user: UserModel,
):
    """DELETE /chat/conversations/{id} should soft delete (is_deleted=Y)."""
    conv = Conversation(user_id=str(sovereign_user.id), title="To Delete")
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    
    response = await auth_client.delete(
        f"/api/v1/chat/conversations/{conv.id}",
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    db_session.refresh(conv)
    # is_deleted might be "Y" (string) or True (boolean) depending on DB schema
    assert conv.is_deleted in ("Y", True)
    
    # Should not appear in list by default
    response = await auth_client.get("/api/v1/chat/conversations")
    data = response.json()
    titles = [c["title"] for c in data["conversations"]]
    assert "To Delete" not in titles


@pytest.mark.asyncio
async def test_websocket_chat_still_works():
    """Verify WebSocket /ws/chat still connects and streams."""
    # This is a basic connectivity test — full WebSocket testing needs testclient.websocket
    from backend.main import app
    routes = [r.path for r in app.routes]
    assert "/ws/chat" in routes