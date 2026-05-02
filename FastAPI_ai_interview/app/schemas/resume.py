"""Resume-related Pydantic schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ResumeUploadResponse(BaseModel):
    resume_id: int
    parsed_data: dict[str, Any]
    position_match_score: int | None = None
    match_feedback: str | None = None


class ResumeDetailResponse(BaseModel):
    id: int
    user_id: int
    file_path: str
    parsed_data: dict[str, Any]
    position: str
    difficulty: str
    position_match_score: int | None = None
    match_feedback: str | None = None
    uploaded_at: datetime
