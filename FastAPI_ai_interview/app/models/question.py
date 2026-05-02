"""Question model (question bank)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    position_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    difficulty: Mapped[str] = mapped_column(
        Enum("初级", "中级", "高级"), nullable=False
    )
    type: Mapped[str] = mapped_column(
        Enum("technical", "behavioral", "situational"), nullable=False
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    scoring_points: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    sample_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_hints: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    skill_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Integer, default=0, index=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, onupdate=func.current_timestamp()
    )

    __table_args__ = (
        {"mysql_charset": "utf8mb4"},
    )
