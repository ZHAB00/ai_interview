"""Interview management endpoints: create, history, report."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import NotFoundException
from app.models.interview import Interview
from app.models.report import Report
from app.models.resume import Resume
from app.models.user import User
from app.schemas.interview import (
    CreateInterviewRequest,
    CreateInterviewResponse,
    InterviewHistoryItem,
    InterviewHistoryResponse,
    ReportStatusResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/interviews", tags=["面试"])


@router.post("", response_model=CreateInterviewResponse, status_code=201)
async def create_interview(
    req: CreateInterviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建面试并返回 WebSocket 凭证。"""
    # Resolve resume: if not provided (quick start), create a placeholder
    if req.resume_id is not None:
        result = await db.execute(
            select(Resume).where(Resume.id == req.resume_id, Resume.user_id == current_user.id)
        )
        resume = result.scalar_one_or_none()
        if not resume:
            raise NotFoundException("简历不存在")
        resume_id = resume.id
    else:
        # Quick start — create a minimal placeholder resume
        placeholder = Resume(
            user_id=current_user.id,
            file_path="",
            parsed_data={
                "name": "快速体验用户",
                "skills": [],
                "position": req.position,
                "quick_start": True,
            },
            position=req.position,
            difficulty=req.difficulty,
        )
        db.add(placeholder)
        await db.flush()
        resume_id = placeholder.id
        logger.info(f"快速体验模式，已创建占位简历: resume_id={resume_id}")

    # Validate mode/stage
    if req.mode == "stage" and not req.selected_stages:
        from app.core.exceptions import ValidationErrorException
        raise ValidationErrorException("阶段练习模式需提供 selected_stages")

    # Create interview record
    interview = Interview(
        user_id=current_user.id,
        resume_id=resume_id,
        position=req.position,
        difficulty=req.difficulty,
        mode=req.mode,
        selected_stages=req.selected_stages or ["初筛", "HR面", "技术面", "终面"],
        status="created",
    )
    db.add(interview)
    await db.commit()
    await db.refresh(interview)

    # Generate ws_token as a self-contained JWT (validates without Redis)
    from app.core.security import create_access_token
    ws_token = create_access_token(
        {"sub": str(current_user.id), "interview_id": interview.id, "type": "ws"},
        expires_delta=15,  # 15-minute window to start the interview
    )
    # Also store in Redis for session management (non-critical)
    try:
        from app.ws.session_manager import session_manager
        await session_manager.store_token(ws_token, interview.id, ttl=900)
    except Exception as e:
        logger.warning(f"Redis token存储失败，将继续: {e}")

    logger.info(f"面试创建成功: interview_id={interview.id}, user_id={current_user.id}")

    return CreateInterviewResponse(
        interview_id=interview.id,
        ws_token=ws_token,
        ws_url=f"/ws/interview/{interview.id}",
        expires_in=900,
    )


@router.get("/history", response_model=InterviewHistoryResponse)
async def get_history(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的面试历史记录。"""
    page_size = min(page_size, 100)

    # Total count
    count_result = await db.execute(
        select(func.count()).select_from(Interview).where(Interview.user_id == current_user.id)
    )
    total = count_result.scalar() or 0

    # Items
    result = await db.execute(
        select(Interview)
        .where(Interview.user_id == current_user.id)
        .order_by(Interview.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    interviews = result.scalars().all()

    items = [
        InterviewHistoryItem(
            interview_id=iv.id,
            position=iv.position,
            difficulty=iv.difficulty,
            mode=iv.mode,
            status=iv.status,
            overall_score=iv.overall_score,
            passed=bool(iv.passed) if iv.passed is not None else None,
            created_at=iv.created_at,
        )
        for iv in interviews
    ]

    return InterviewHistoryResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{interview_id}/report", response_model=ReportStatusResponse)
async def get_report(
    interview_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取面试报告。面试结束后调用。"""
    # Verify interview ownership
    result = await db.execute(
        select(Interview).where(
            Interview.id == interview_id, Interview.user_id == current_user.id
        )
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise NotFoundException("面试不存在")

    # Get report
    result = await db.execute(
        select(Report).where(Report.interview_id == interview_id)
    )
    report = result.scalar_one_or_none()

    if not report or report.status == "generating":
        return ReportStatusResponse(status="generating")
    elif report.status == "error":
        return ReportStatusResponse(status="generating")
    else:
        return ReportStatusResponse(status="completed", report=report.report_data)
