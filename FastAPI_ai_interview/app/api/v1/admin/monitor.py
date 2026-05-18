"""Admin real-time monitoring endpoints."""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin, get_db
from app.models.user import User
from app.models.interview import Interview
from app.ws.session_manager import session_manager
from app.schemas.admin import (
    MonitorUserItem,
    MonitorUserListResponse,
    MonitorInterviewItem,
    MonitorInterviewListResponse,
    MonitorSummaryResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/monitor", tags=["管理后台-实时监控"])

ONLINE_WINDOW_MINUTES = 2


@router.get("/users", response_model=MonitorUserListResponse)
async def list_users_for_monitor(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """返回所有用户及其在线状态。"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=ONLINE_WINDOW_MINUTES)

    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    # Count interviews per user
    interview_counts = {}
    active_interviews = {}
    if users:
        user_ids = [u.id for u in users]
        count_result = await db.execute(
            select(Interview.user_id, func.count(Interview.id))
            .where(Interview.user_id.in_(user_ids))
            .group_by(Interview.user_id)
        )
        for row in count_result:
            interview_counts[row[0]] = row[1]

        active_result = await db.execute(
            select(Interview).where(
                Interview.user_id.in_(user_ids),
                Interview.status == "in_progress",
                Interview.deleted_at.is_(None),
            )
        )
        for iv in active_result.scalars().all():
            active_interviews[iv.user_id] = {
                "interview_id": iv.id,
                "position": iv.position,
            }

    items = []
    online_count = 0
    for u in users:
        is_online = u.last_active_at is not None and u.last_active_at > cutoff
        if is_online:
            online_count += 1
        items.append(MonitorUserItem(
            user_id=u.id,
            username=u.username,
            role=u.role,
            is_online=is_online,
            last_active_at=u.last_active_at,
            created_at=u.created_at,
            interview_count=interview_counts.get(u.id, 0),
            active_interview=active_interviews.get(u.id),
        ))

    return MonitorUserListResponse(
        items=items,
        total=len(items),
        online_count=online_count,
    )


@router.get("/interviews", response_model=MonitorInterviewListResponse)
async def list_interviews_for_monitor(
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """返回所有面试记录，在线的排最前面。"""
    page_size = min(page_size, 200)
    now = datetime.now(timezone.utc)

    # Get active WS interview IDs
    active_ids = await session_manager.list_active_interview_ids()
    active_id_set = set(active_ids) if active_ids else set()

    # Query total
    count_result = await db.execute(
        select(func.count()).select_from(Interview).where(
            Interview.deleted_at.is_(None)
        )
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Interview)
        .options(selectinload(Interview.user))
        .where(Interview.deleted_at.is_(None))
        .order_by(Interview.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    interviews = result.scalars().all()

    items = []
    for iv in interviews:
        duration = None
        if iv.started_at and iv.status == "in_progress":
            duration = int((now - iv.started_at).total_seconds())

        items.append(MonitorInterviewItem(
            interview_id=iv.id,
            username=iv.user.username if iv.user else "未知",
            position=iv.position,
            difficulty=iv.difficulty,
            mode=iv.mode,
            status=iv.status,
            current_stage=iv.current_stage,
            started_at=iv.started_at,
            duration_seconds=duration,
            is_ws_connected=iv.id in active_id_set,
            created_at=iv.created_at,
        ))

    # Sort: WS-connected first
    items.sort(key=lambda x: x.is_ws_connected, reverse=True)

    return MonitorInterviewListResponse(items=items, total=total)


@router.get("/summary", response_model=MonitorSummaryResponse)
async def get_monitor_summary(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """返回概览统计数字。"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=ONLINE_WINDOW_MINUTES)

    total_users_result = await db.execute(
        select(func.count()).select_from(User)
    )
    total_users = total_users_result.scalar() or 0

    online_users_result = await db.execute(
        select(func.count()).select_from(User).where(
            User.last_active_at.isnot(None),
            User.last_active_at > cutoff,
        )
    )
    online_users = online_users_result.scalar() or 0

    total_interviews_result = await db.execute(
        select(func.count()).select_from(Interview).where(
            Interview.deleted_at.is_(None)
        )
    )
    total_interviews = total_interviews_result.scalar() or 0

    active_interviews_result = await db.execute(
        select(func.count()).select_from(Interview).where(
            Interview.status == "in_progress",
            Interview.deleted_at.is_(None),
        )
    )
    active_interviews = active_interviews_result.scalar() or 0

    return MonitorSummaryResponse(
        online_users=online_users,
        total_users=total_users,
        active_interviews=active_interviews,
        total_interviews=total_interviews,
    )
