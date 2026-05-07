"""Interview model."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    resume_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resumes.id"), nullable=False
    )
    position: Mapped[str] = mapped_column(String(100), nullable=False)
    difficulty: Mapped[str] = mapped_column(
        Enum("初级", "中级", "高级"), nullable=False
    )
    mode: Mapped[str] = mapped_column(
        Enum("full", "stage"), nullable=False
    )
    selected_stages: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("created", "in_progress", "completed", "abandoned"),
        nullable=False,
        default="created",
        index=True,
    )
    answers: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    resume_deduction: Mapped[int | None] = mapped_column(Integer, default=0)
    deduction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Integer, nullable=True)  # TINYINT
    current_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_favorited: Mapped[bool] = mapped_column(Integer, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(), index=True
    )

    # Relationships
    user = relationship("User", back_populates="interviews")
    resume = relationship("Resume", back_populates="interviews")
    report = relationship("Report", back_populates="interview", uselist=False)
