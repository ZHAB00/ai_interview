"""Admin-related Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


# ── Document ──

class DocumentUploadResponse(BaseModel):
    document_id: int
    status: str = "processing"
    message: str = "文档已上传，正在向量化处理，请稍后查询状态"


class DocumentStatusResponse(BaseModel):
    document_id: int
    filename: str
    description: str | None = None
    status: str  # processing | ready | error
    chunks_count: int | None = None
    created_at: datetime


class DocumentListItem(BaseModel):
    id: int
    filename: str
    description: str | None = None
    tags: list[str] | None = None
    status: str
    chunks_count: int | None = None
    created_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]
    total: int
    page: int
    page_size: int


# ── User Management ──

class AdminUserItem(BaseModel):
    id: int
    phone: str
    username: str
    role: str
    created_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserItem]
    total: int
    page: int
    page_size: int


# ── Feedback ──


class FeedbackCreateRequest(BaseModel):
    question_index: int = Field(ge=0)
    error_index: int = Field(ge=0)
    feedback_type: str = Field(pattern=r"^(fact_error|score_unfair|other)$")
    comment: str | None = None


class FeedbackCreateResponse(BaseModel):
    status: str = "recorded"
    feedback_id: int


# ── Invite Codes ──


class CreateInviteCodeRequest(BaseModel):
    duration_hours: float = Field(gt=0)
    max_uses: int | None = Field(default=None, ge=1)


class InviteCodeItem(BaseModel):
    id: int
    code: str
    max_uses: int | None
    use_count: int
    expires_at: datetime
    is_active: bool
    created_at: datetime


class InviteCodeListResponse(BaseModel):
    items: list[InviteCodeItem]


# ── Monitor ──

class MonitorUserItem(BaseModel):
    user_id: int
    username: str
    role: str
    is_online: bool
    last_active_at: datetime | None
    interview_count: int
    active_interview: dict | None  # {interview_id, position}


class MonitorUserListResponse(BaseModel):
    items: list[MonitorUserItem]
    total: int
    online_count: int


class MonitorInterviewItem(BaseModel):
    interview_id: int
    username: str
    position: str
    difficulty: str
    mode: str
    status: str
    current_stage: str | None
    started_at: datetime | None
    duration_seconds: int | None
    is_ws_connected: bool
    created_at: datetime


class MonitorInterviewListResponse(BaseModel):
    items: list[MonitorInterviewItem]
    total: int


class MonitorSummaryResponse(BaseModel):
    online_users: int
    total_users: int
    active_interviews: int
    total_interviews: int
