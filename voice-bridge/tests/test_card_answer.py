import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main as bridge


def _sample_card():
    return {
        "card_id": "card-test-1",
        "card_group_id": "grp-1",
        "title": "Project setup",
        "questions": [
            {
                "id": "q1",
                "question": "Which environment should we target?",
                "input_type": "single_select",
                "required": True,
                "options": [
                    {"id": "a", "label": "Production", "value": "production"},
                    {"id": "b", "label": "Staging", "value": "staging"},
                    {"id": "c", "label": "Development", "value": "development"},
                ],
            },
            {
                "id": "q2",
                "question": "Should we notify the team?",
                "input_type": "single_select",
                "required": True,
                "options": [
                    {"id": "y", "label": "Yes", "value": "yes"},
                    {"id": "n", "label": "No", "value": "no"},
                ],
            },
        ],
    }


def test_build_card_answer_selects_matching_option():
    card = _sample_card()
    answer = bridge._build_card_answer(card, "Let's go with Staging please")
    assert answer["card_id"] == "card-test-1"
    assert answer["card_group_id"] == "grp-1"
    q1 = answer["answers"][0]
    assert q1["question_id"] == "q1"
    assert q1["selected_option_ids"] == ["b"]
    assert q1["other_text"] is None


def test_build_card_answer_non_matching_lands_in_other_text():
    card = _sample_card()
    answer = bridge._build_card_answer(card, "I think we should use the canary cluster")
    q1 = answer["answers"][0]
    assert q1["selected_option_ids"] == []
    assert q1["other_text"] == "I think we should use the canary cluster"


def test_build_card_answer_value_match():
    card = _sample_card()
    answer = bridge._build_card_answer(card, "production")
    assert answer["answers"][0]["selected_option_ids"] == ["a"]


def test_card_to_speech_text_contains_question():
    card = _sample_card()
    text = bridge._card_to_speech_text(card)
    assert "Project setup" in text
    assert "Which environment should we target?" in text
    assert "Production" in text
    assert "Staging" in text
    assert "Development" in text


def test_token_matching_avoids_substring_false_positives():
    # Whole-word (token) matching must not let "no" match inside "none"/"now"
    # nor "yes" inside "yesterday".
    card = _sample_card()
    ans = bridge._build_card_answer(card, "I will do it now")
    q2 = ans["answers"][1]
    assert q2["selected_option_ids"] == []
    assert q2["other_text"] == "I will do it now"

    ans2 = bridge._build_card_answer(card, "we discussed it yesterday")
    assert ans2["answers"][1]["selected_option_ids"] == []
    assert ans2["answers"][1]["other_text"] == "we discussed it yesterday"

    # A real "no"/"yes" token must still match.
    assert bridge._build_card_answer(card, "no")["answers"][1]["selected_option_ids"] == ["n"]
    assert bridge._build_card_answer(card, "yes")["answers"][1]["selected_option_ids"] == ["y"]
