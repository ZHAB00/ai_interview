"""Interview management endpoints: create, history, report, reconnect, delete, favorite."""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.exceptions import ConflictException, NotFoundException, ValidationErrorException
from app.models.interview import Interview
from app.models.report import Report
from app.models.resume import Resume
from app.models.user import User
from app.schemas.interview import (
    CreateInterviewRequest,
    CreateInterviewResponse,
    InterviewHistoryItem,
    InterviewHistoryResponse,
    JDAnalyzeRequest,
    ReportStatusResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/interviews", tags=["面试"])

MAX_VISIBLE = 20
SOFT_DELETE_RETENTION_DAYS = 7


def _cleanup_stale_interview(interview: Interview) -> bool:
    """If interview exceeded max duration, mark completed. Returns True if cleaned."""
    if interview.status == "in_progress" and interview.started_at:
        now_utc = datetime.now(timezone.utc)
        started = interview.started_at.replace(tzinfo=timezone.utc)
        elapsed = (now_utc - started).total_seconds()
        if elapsed >= settings.INTERVIEW_MAX_DURATION:
            interview.status = "completed"
            interview.ended_at = datetime.now(timezone.utc)
            return True
    return False


async def _trim_history(user_id: int, db: AsyncSession):
    """Keep at most MAX_VISIBLE non-favorited, non-deleted interviews.
    Soft-delete the oldest exceeding ones.
    Hard-delete records soft-deleted more than SOFT_DELETE_RETENTION_DAYS ago.
    """
    # Hard-delete old soft-deleted records
    cutoff = datetime.now(timezone.utc) - timedelta(days=SOFT_DELETE_RETENTION_DAYS)
    old_deleted = await db.execute(
        select(Interview)
        .options(selectinload(Interview.report))
        .where(
            Interview.user_id == user_id,
            Interview.deleted_at.isnot(None),
            Interview.deleted_at < cutoff,
        )
    )
    for rec in old_deleted.scalars().all():
        logger.info(f"硬删除过期记录: interview_id={rec.id}")
        # Delete associated report first to avoid FK constraint (SET NULL on NOT NULL column)
        if rec.report:
            await db.delete(rec.report)
        await db.delete(rec)

    # Count visible records (not deleted, not favorited)
    visible_count = await db.execute(
        select(func.count()).select_from(Interview).where(
            Interview.user_id == user_id,
            Interview.deleted_at.is_(None),
            Interview.is_favorited == 0,
        )
    )
    total_visible = visible_count.scalar() or 0

    if total_visible > MAX_VISIBLE:
        excess = total_visible - MAX_VISIBLE
        old_result = await db.execute(
            select(Interview).where(
                Interview.user_id == user_id,
                Interview.deleted_at.is_(None),
                Interview.is_favorited == 0,
            )
            .order_by(Interview.created_at.asc())
            .limit(excess)
        )
        for rec in old_result.scalars().all():
            rec.deleted_at = datetime.now(timezone.utc)
            logger.info(f"软删除超限记录: interview_id={rec.id}")


@router.post("/analyze-jd", response_model=dict)
async def analyze_jd(
    req: "JDAnalyzeRequest",
    current_user: User = Depends(get_current_user),
):
    """分析招聘JD：提取岗位和技能要求。"""
    from app.agents.base import BaseAgent

    class JDAgent(BaseAgent):
        @property
        def system_prompt(self) -> str:
            return (
                "你是一个招聘需求分析专家。从JD中提取关键信息。\n"
                "请严格按照 JSON 格式返回：\n"
                '{"position": "岗位名称", "skills": ["技能1", "技能2"], '
                '"requirements": ["职责要求1", "职责要求2"]}\n'
                "skills 仅包含具体技术栈（如Python/MySQL/K8s），英文，不超过10个。\n"
                "若JD中有'至少掌握其中一种'的条件，skills中只列出即可，"
                "同时在requirements的第一条标注为'条件满足：掌握X/Y/Z中至少一种'。\n"
                "requirements 为核心职责/经验要求，中文，不超过5条。\n"
                "position 为最匹配的岗位名称（中文，如'后端开发工程师'）。"
            )

    try:
        agent = JDAgent()
        result = await agent.llm_call_json([{
            "role": "user",
            "content": f"请分析以下招聘JD：\n\n{req.jd_text[:3000]}",
        }])
        return {
            "position": result.get("position", ""),
            "skills": result.get("skills", []),
            "requirements": result.get("requirements", []),
        }
    except Exception as e:
        logger.error(f"JD分析失败: {e}", exc_info=True)
        raise ValidationErrorException("JD分析失败，请检查文本后重试")


@router.post("", response_model=CreateInterviewResponse, status_code=201)
async def create_interview(
    req: CreateInterviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建面试并返回 WebSocket 凭证。"""
    if req.resume_id is not None:
        result = await db.execute(
            select(Resume).where(Resume.id == req.resume_id, Resume.user_id == current_user.id)
        )
        resume = result.scalar_one_or_none()
        if not resume:
            raise NotFoundException("简历不存在")
        resume_id = resume.id
    else:
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

    if req.mode == "stage" and not req.selected_stages:
        raise ValidationErrorException("阶段练习模式需提供 selected_stages")

    # Clear previous in_progress interviews for this user
    stale_result = await db.execute(
        select(Interview).where(
            Interview.user_id == current_user.id,
            Interview.status == "in_progress",
        )
    )
    stale_interviews = stale_result.scalars().all()
    for stale in stale_interviews:
        if _cleanup_stale_interview(stale):
            logger.info(f"清理超时面试: interview_id={stale.id}")
        else:
            stale.status = "abandoned"
            stale.ended_at = datetime.now(timezone.utc)
            logger.info(f"放弃旧面试: interview_id={stale.id}")

    # Abandon created-but-never-entered interviews
    created_result = await db.execute(
        select(Interview).where(
            Interview.user_id == current_user.id,
            Interview.status == "created",
        )
    )
    for created in created_result.scalars().all():
        created.status = "abandoned"
        created.ended_at = datetime.now(timezone.utc)
        logger.info(f"废弃未开始面试: interview_id={created.id}")

    interview = Interview(
        user_id=current_user.id,
        resume_id=resume_id,
        position=req.position,
        difficulty=req.difficulty,
        mode=req.mode,
        selected_stages=req.selected_stages or ["初筛", "HR面", "技术面", "终面"],
        jd_text=req.jd_text[:3000] if req.jd_text else None,
        jd_analysis=req.jd_analysis,
        status="created",
    )
    db.add(interview)
    await db.flush()

    # Trim history: keep at most MAX_VISIBLE visible records
    await _trim_history(current_user.id, db)
    await db.commit()
    await db.refresh(interview)

    from app.core.security import create_access_token
    ws_token = create_access_token(
        {"sub": str(current_user.id), "interview_id": interview.id, "type": "ws"},
        expires_delta=15,
    )
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


@router.get("/active")
async def get_active_interview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前进行中的面试（用于断线恢复）。自动清理超时面试。"""
    result = await db.execute(
        select(Interview).where(
            Interview.user_id == current_user.id,
            Interview.status == "in_progress",
            Interview.deleted_at.is_(None),
        )
    )
    interview = result.scalars().all()

    active = None
    for iv in interview:
        if _cleanup_stale_interview(iv):
            await db.commit()
        else:
            active = iv

    if not active:
        return {"active": False, "interview_id": None}

    started = active.started_at.replace(tzinfo=timezone.utc) if active.started_at else datetime.now(timezone.utc)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    remaining = max(0, settings.INTERVIEW_MAX_DURATION - int(elapsed))
    return {
        "active": True,
        "interview_id": active.id,
        "position": active.position,
        "stage": active.current_stage,
        "mode": active.mode,
        "started_at": active.started_at.isoformat() if active.started_at else None,
        "remaining_seconds": remaining,
    }


@router.post("/{interview_id}/reconnect")
async def reconnect_interview(
    interview_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取新的 ws_token 用于断线重连。"""
    result = await db.execute(
        select(Interview).where(
            Interview.id == interview_id,
            Interview.user_id == current_user.id,
            Interview.status == "in_progress",
        )
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise NotFoundException("面试不存在或已结束")

    if _cleanup_stale_interview(interview):
        await db.commit()
        raise NotFoundException("面试已超时")

    from app.core.security import create_access_token
    ws_token = create_access_token(
        {"sub": str(current_user.id), "interview_id": interview.id, "type": "ws"},
        expires_delta=15,
    )
    try:
        from app.ws.session_manager import session_manager
        await session_manager.store_token(ws_token, interview.id, ttl=900)
    except Exception as e:
        logger.warning(f"Redis token存储失败: {e}")

    return {
        "interview_id": interview.id,
        "ws_token": ws_token,
        "ws_url": f"/ws/interview/{interview.id}",
        "expires_in": 900,
    }


@router.get("/history", response_model=InterviewHistoryResponse)
async def get_history(
    page: int = 1,
    page_size: int = 8,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的面试历史记录（分页）。favorited 优先显示，不展示已删除。"""
    page_size = min(page_size, 20)

    count_result = await db.execute(
        select(func.count()).select_from(Interview).where(
            Interview.user_id == current_user.id,
            Interview.deleted_at.is_(None),
        )
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Interview)
        .where(
            Interview.user_id == current_user.id,
            Interview.deleted_at.is_(None),
        )
        .order_by(Interview.is_favorited.desc(), Interview.created_at.desc())
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
            is_favorited=bool(iv.is_favorited),
            created_at=iv.created_at,
        )
        for iv in interviews
    ]

    return InterviewHistoryResponse(items=items, total=total, page=page, page_size=page_size)


@router.put("/{interview_id}/favorite")
async def toggle_favorite(
    interview_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """收藏/取消收藏面试。最多收藏 5 个。"""
    result = await db.execute(
        select(Interview).where(
            Interview.id == interview_id,
            Interview.user_id == current_user.id,
        )
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise NotFoundException("面试不存在")

    if interview.is_favorited:
        interview.is_favorited = False
        await db.commit()
        return {"favorited": False, "message": "已取消收藏"}
    else:
        # Check limit
        fav_count = await db.execute(
            select(func.count()).select_from(Interview).where(
                Interview.user_id == current_user.id,
                Interview.is_favorited == 1,
                Interview.deleted_at.is_(None),
            )
        )
        if (fav_count.scalar() or 0) >= 5:
            raise ConflictException("最多收藏 5 个面试")
        interview.is_favorited = True
        await db.commit()
        return {"favorited": True, "message": "已收藏"}


@router.delete("/{interview_id}", status_code=200)
async def delete_interview(
    interview_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """硬删除面试（含报告和录音文件）。收藏的面试不可删除。"""
    result = await db.execute(
        select(Interview).where(
            Interview.id == interview_id,
            Interview.user_id == current_user.id,
        )
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise NotFoundException("面试不存在")

    if interview.is_favorited:
        raise ConflictException("收藏的面试不可删除，请先取消收藏")

    # Delete audio files
    if interview.answers:
        try:
            answers = json.loads(interview.answers) if isinstance(interview.answers, str) else interview.answers
            for ans in answers:
                audio_url = ans.get("user_audio_url", "")
                if audio_url and audio_url.startswith("/uploads/audio/"):
                    filename = audio_url.split("/")[-1].split("?")[0]
                    audio_path = Path(settings.UPLOAD_DIR) / "audio" / filename
                    if audio_path.exists():
                        audio_path.unlink()
        except Exception as e:
            logger.warning(f"删除音频文件失败: {e}")

    # Delete report
    result = await db.execute(select(Report).where(Report.interview_id == interview_id))
    report = result.scalar_one_or_none()
    if report:
        await db.delete(report)

    # Delete interview
    await db.delete(interview)
    await db.commit()
    logger.info(f"面试已删除: interview_id={interview_id}")
    return {"message": "面试已删除"}


@router.get("/{interview_id}/report", response_model=ReportStatusResponse)
async def get_report(
    interview_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取面试报告。面试结束后调用。"""
    result = await db.execute(
        select(Interview).where(
            Interview.id == interview_id, Interview.user_id == current_user.id
        )
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise NotFoundException("面试不存在")

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
