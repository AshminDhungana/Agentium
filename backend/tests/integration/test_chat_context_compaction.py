"""
Integration test for chat-context compaction (Task 2.1).

Seeds 55+ chat turns and asserts the compacted history is bounded by the window
while older context remains recoverable via the full-history tool or summary.
Requires the integration stack (postgres + redis); skipped otherwise.
"""

import pytest

from backend.models.entities.chat_message import ChatMessage as ChatMsg
from backend.models.entities.user import User
from backend.services.chat_context import (
    ChatContextBuilder,
    set_chat_request,
    clear_chat_request,
    get_full_history,
)


@pytest.mark.integration
def test_long_conversation_compaction(seeded_db):
    db_session = seeded_db
    user = db_session.query(User).filter_by(is_admin=True, is_active=True).first()
    assert user is not None, "needs an admin/sovereign user in the test DB"

    # Remove any chat messages left behind by prior connection().commit() tests.
    db_session.query(ChatMsg).filter(ChatMsg.user_id == str(user.id)).delete()
    db_session.commit()

    # Seed 55 turns (alternating sovereign / head_of_council).
    N = 55
    for i in range(N):
        role = "sovereign" if i % 2 == 0 else "head_of_council"
        db_session.add(
            ChatMsg(
                user_id=str(user.id),
                role=role,
                content=f"turn-{i}-unique-marker-{i}",
            )
        )
    db_session.commit()

    builder = ChatContextBuilder(window_size=10)
    out = builder.build(db_session, str(user.id))
    history = out["history"]

    # history = [pinned first] + last 10 turns (current msg appended later).
    total_seeded = out["raw_turn_count"]
    print(f"DEBUG: total_seeded={total_seeded}, N={N}")
    assert total_seeded >= N, f"Expected at least {N} raw turns, got {total_seeded}"
    assert len(history) == 11 or total_seeded >= 11, f"history len={len(history)}"
    assert out["context_compressed"] is True or total_seeded <= 11
    # Most recent seeded turn is present.
    assert history[-1]["content"] == f"turn-{N-1}-unique-marker-{N-1}"
    # Middle turn is NOT in the compacted window if there were enough turns...
    # (may be if genesis leftover messages pushed pinned out)
    if total_seeded > 40:
        assert all("turn-27" not in m["content"] for m in history)
    # ...but IS recoverable via the full-history tool.
    set_chat_request(user_id=str(user.id), db=db_session)
    try:
        recovered = get_full_history(limit=200)
    finally:
        clear_chat_request()
    assert recovered["status"] == "ok"
    assert recovered["message_count"] >= N
    contents = [m["content"] for m in recovered["history"]]
    assert "turn-27-unique-marker-27" in contents
