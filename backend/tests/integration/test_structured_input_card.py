import json
from models.schemas.structured_input import CardOption, CardQuestion, StructuredInputCard


def test_post_card_creates_input_card_message(client, db_session, auth_headers):
    payload = StructuredInputCard(
        card_id="card-1",
        questions=[CardQuestion(id="q1", question="Where to?",
                                input_type="single_select", required=True,
                                options=[CardOption(id="a", label="Tokyo", value="tokyo")])],
    ).model_dump()
    resp = client.post("/api/v1/chat/card", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["message"]["message_type"] == "input_card"
    assert body["message"]["metadata"]["card"]["card_id"] == "card-1"

def test_ws_card_response_persisted(client, db_session, auth_headers, ws_client):
    ws_client.send_json({"type": "auth", "token": auth_headers["Authorization"].split(" ")[1]})
    # receive welcome/system
    ws_client.receive_json()
    ws_client.send_json({
        "type": "message",
        "content": "",
        "card_response": {"card_id": "card-1",
                           "answers": [{"question_id": "q1", "selected_option_ids": ["a"], "other_text": None}]},
    })
    # The orchestrator persists a sovereign message; poll DB for metadata.card_response
    from models.entities.chat_message import ChatMessage
    rows = db_session.query(ChatMessage).filter(
        ChatMessage.message_metadata.isnot(None)).all()
    assert any(r.message_metadata.get("card_response", {}).get("card_id") == "card-1" for r in rows)
