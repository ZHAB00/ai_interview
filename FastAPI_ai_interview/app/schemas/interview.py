"""Interview-related Pydantic schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateInterviewRequest(BaseModel):
    resume_id: int | None = None
    position: str = Field(..., min_length=1)
    difficulty: str = Field(default="中级", pattern=r"^(初级|中级|高级)$")
    mode: str = Field(default="full", pattern=r"^(full|stage)$")
    selected_stages: list[str] | None = None
    jd_text: str | None = None
    jd_analysis: dict[str, Any] | None = None


class JDAnalyzeRequest(BaseModel):
    jd_text: str = Field(..., min_length=20, max_length=3000)


class JDAnalyzeResponse(BaseModel):
    position: str
    skills: list[str]
    requirements: list[str]
    found_in_list: bool = False


class CreateInterviewResponse(BaseModel):
    interview_id: int
    ws_token: str
    ws_url: str
    expires_in: int = 300


class InterviewHistoryItem(BaseModel):
    interview_id: int
    position: str
    difficulty: str
    mode: str
    status: str
    overall_score: int | None = None
    passed: bool | None = None
    is_favorited: bool = False
    created_at: datetime


class InterviewHistoryResponse(BaseModel):
    items: list[InterviewHistoryItem]
    total: int
    page: int
    page_size: int


class ReportStatusResponse(BaseModel):
    status: str  # "generating" | "completed" | "error"
    report: dict[str, Any] | None = None
    error_message: str | None = None
