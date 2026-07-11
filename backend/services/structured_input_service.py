from __future__ import annotations
from typing import List
from models.schemas.structured_input import CardQuestion, StructuredInputCard

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
