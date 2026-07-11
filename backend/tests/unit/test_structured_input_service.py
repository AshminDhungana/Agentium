from models.schemas.structured_input import CardOption, CardQuestion, StructuredInputCard
from services.structured_input_service import render_external_text, chunk_questions

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
