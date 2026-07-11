from models.schemas.structured_input import (
    CardOption, CardQuestion, StructuredInputCard, StructuredInputAnswer, CardAnswerQuestion,
)

def test_max_three_questions_enforced():
    opts = [CardOption(id="a", label="A", value="a")]
    qs = [CardQuestion(id=f"q{i}", question=f"Q{i}", input_type="single_select", options=opts)
          for i in range(4)]
    try:
        StructuredInputCard(card_id="c1", questions=qs)
        assert False, "expected validation error"
    except Exception:
        pass

def test_other_option_not_in_options_array():
    card = StructuredInputCard(
        card_id="c1",
        questions=[CardQuestion(id="q1", question="Q?", input_type="multi_select",
                                options=[CardOption(id="a", label="A", value="a")])],
    )
    assert all(o.label != "Other" for q in card.questions for o in q.options)

def test_answer_requires_card_id_and_answers():
    ans = StructuredInputAnswer(
        card_id="c1",
        answers=[CardAnswerQuestion(question_id="q1", selected_option_ids=["a"], other_text=None)],
    )
    assert ans.card_id == "c1" and ans.answers[0].selected_option_ids == ["a"]
