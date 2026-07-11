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