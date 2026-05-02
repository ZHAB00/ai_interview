"""Feedback endpoints for reporting scoring errors."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import NotFoundException
from app.models.feedback import Feedback
from app.models.interview import Interview
from app.models.user import User
from app.schemas.admin import FeedbackCreateRequest, FeedbackCreateResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feedback", tags=["反馈"])


@router.post("/{interview_id}", response_model=FeedbackCreateResponse, status_code=201)
async def submit_feedback(
    interview_id: int,
    req: FeedbackCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交对评分错误的反馈/纠正。"""
    # Verify interview belongs to user
    result = await db.execute(
        select(Interview).where(
            Interview.id == interview_id, Interview.user_id == current_user.id
        )
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise NotFoundException("面试不存在")

    feedback = Feedback(
        interview_id=interview_id,
        question_index=req.question_index,
        error_index=req.error_index,
        feedback_type=req.feedback_type,
        comment=req.comment,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    logger.info(
        f"反馈已提交: interview_id={interview_id}, feedback_id={feedback.id}, type={req.feedback_type}"
    )

    return FeedbackCreateResponse(feedback_id=feedback.id)
