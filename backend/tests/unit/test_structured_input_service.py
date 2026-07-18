from models.schemas.structured_input import CardOption, CardQuestion, StructuredInputCard
from services.structured_input_service import render_external_text, chunk_questions, parse_card_answer

def _q(qid):
    return CardQuestion(id=qid, question=f"{qid}?", input_type="single_select",
                        options=[CardOption(id="a", label="Tokyo", value="tokyo"),
                                 CardOption(id="b", label="Paris", value="paris")])

def test_render_external_text_numbers_and_letters():
    card = StructuredInputCard(card_id="c1", questions=[_q("q1"), _q("q2")])
    out = render_external_text(card)
    assert "1. q1?" in out and "   a) Tokyo" in out and "   Other (type your answer)" in out
    assert "2. q2?" in out

def test_chunk_questions_splits_over_three():
    chunked = chunk_questions([_q(f"q{i}") for i in range(5)], size=3)
    assert [len(c) for c in chunked] == [3, 2]

def test_parse_card_answer_numbered():
    card = StructuredInputCard(
        card_id="c1",
        questions=[
            CardQuestion(id="q1", question="Color?", input_type="single_select", required=True,
                         options=[CardOption(id="a", label="Red", value="red"),
                                  CardOption(id="b", label="Blue", value="blue")]),
            CardQuestion(id="q2", question="Size?", input_type="single_select", required=False,
                         options=[CardOption(id="s", label="S", value="s"),
                                  CardOption(id="l", label="L", value="l")]),
        ],
    )
    ans = parse_card_answer("1a\n2l", card)
    assert ans.card_id == "c1"
    by_q = {a.question_id: a for a in ans.answers}
    assert by_q["q1"].selected_option_ids == ["a"]
    assert by_q["q2"].selected_option_ids == ["l"]
