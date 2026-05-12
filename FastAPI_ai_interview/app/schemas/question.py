"""Question bank Pydantic schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ScoringPoint(BaseModel):
    point: str
    max_score: int


class CreateQuestionRequest(BaseModel):
    stage: str
    position_tags: list[str]
    difficulty: str = Field(pattern=r"^(初级|中级|高级)$")
    type: str = Field(pattern=r"^(technical|behavioral|situational)$")
    question_text: str
    dimensions: list[str]
    scoring_points: list[ScoringPoint]
    sample_answer: str | None = None
    follow_up_hints: list[str] | None = None
    tags: list[str] | None = None
    skill_tags: list[str] | None = None
    source: str = "manual"


class UpdateQuestionRequest(BaseModel):
    stage: str | None = None
    position_tags: list[str] | None = None
    difficulty: str | None = Field(default=None, pattern=r"^(初级|中级|高级)$")
    type: str | None = Field(default=None, pattern=r"^(technical|behavioral|situational)$")
    question_text: str | None = None
    dimensions: list[str] | None = None
    scoring_points: list[ScoringPoint] | None = None
    sample_answer: str | None = None
    follow_up_hints: list[str] | None = None
    tags: list[str] | None = None
    skill_tags: list[str] | None = None


class QuestionResponse(BaseModel):
    id: int
    stage: str
    position_tags: list[str]
    difficulty: str
    type: str
    question_text: str
    dimensions: list[str]
    scoring_points: list[dict[str, Any]]
    sample_answer: str | None = None
    follow_up_hints: list[str] | None = None
    tags: list[str] | None = None
    skill_tags: list[str] | None = None
    source: str = "manual"
    source_interview_id: int | None = None
    is_deleted: bool = False
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime | None = None


class QuestionListResponse(BaseModel):
    items: list[QuestionResponse]
    total: int
    page: int
    page_size: int
