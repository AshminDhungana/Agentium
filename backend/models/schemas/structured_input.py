from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class CardOption(BaseModel):
    id: str
    label: str
    value: str


class CardQuestion(BaseModel):
    id: str
    question: str
    input_type: Literal["single_select", "multi_select"]
    required: bool = True
    options: list[CardOption]


class StructuredInputCard(BaseModel):
    card_id: str
    card_group_id: Optional[str] = None  # links sequential cards when >3 questions are chunked
    title: Optional[str] = None
    questions: list[CardQuestion] = Field(..., min_length=1, max_length=3)
    expires_at: Optional[str] = None  # ISO-8601; omission = no expiry


class CardAnswerQuestion(BaseModel):
    question_id: str
    selected_option_ids: list[str] = Field(default_factory=list)  # excludes "Other"
    other_text: Optional[str] = None  # present iff "Other" chosen


class StructuredInputAnswer(BaseModel):
    card_id: str
    card_group_id: Optional[str] = None
    answers: list[CardAnswerQuestion] = Field(..., min_length=1)
