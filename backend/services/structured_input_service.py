from __future__ import annotations
from typing import List, Optional
from models.schemas.structured_input import CardQuestion, StructuredInputCard, StructuredInputAnswer, CardAnswerQuestion

LETTERS = "abcdefghijklmnopqrstuvwxyz"


def render_external_text(card: StructuredInputCard) -> str:
    """Plain-text fallback for WhatsApp/SMS/email: numbered questions, lettered options."""
    lines: List[str] = []
    if card.title:
        lines.append(card.title)
    for i, q in enumerate(card.questions, start=1):
        lines.append(f"{i}. {q.question}")
        for j, opt in enumerate(q.options):
            letter = LETTERS[j] if j < len(LETTERS) else str(j)
            lines.append(f"   {letter}) {opt.label}")
        lines.append("   Other (type your answer)")
    lines.append("")
    lines.append("Reply with one line per question (e.g. '1a' then '2c').")
    return "\n".join(lines)


def chunk_questions(questions: List[CardQuestion], size: int = 3) -> List[List[CardQuestion]]:
    """Split >3 questions into sequential batches, each <= size (spec hard cap = 3)."""
    if size < 1:
        raise ValueError("size must be >= 1")
    return [questions[i:i + size] for i in range(0, len(questions), size)]


def parse_card_answer(text: str, card: StructuredInputCard) -> StructuredInputAnswer:
    """Parse a plain-text channel reply (e.g. '1a\\n2l') into a structured answer.

    Mirrors the format emitted by render_external_text: one line per question,
    each line '<n><letter>' (n = question number, letter = option letter). Lines
    that don't match an option become the 'Other' free-text answer for that
    question.
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    answers: List[CardAnswerQuestion] = []
    for i, q in enumerate(card.questions, start=1):
        raw = next((ln for ln in lines if ln.lower().startswith(f"{i}")), None)
        selected: List[str] = []
        other: Optional[str] = None
        if raw:
            token = raw[1:].strip().lower()
            matched = False
            for j, opt in enumerate(q.options):
                letter = LETTERS[j] if j < len(LETTERS) else str(j)
                if token == letter or token == opt.value.lower() or token == opt.label.lower():
                    selected.append(opt.id)
                    matched = True
            if not matched:
                other = raw
        answers.append(CardAnswerQuestion(
            question_id=q.id,
            selected_option_ids=selected,
            other_text=other,
        ))
    return StructuredInputAnswer(
        card_id=card.card_id,
        card_group_id=card.card_group_id,
        answers=answers,
    )
