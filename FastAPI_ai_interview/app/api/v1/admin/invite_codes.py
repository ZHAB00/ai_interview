"""Admin invite code management — create, list, deactivate time-limited codes."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.core.exceptions import NotFoundException
from app.models.invite_code import InviteCode
from app.models.user import User
from app.schemas.admin import CreateInviteCodeRequest, InviteCodeItem, InviteCodeListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/invite-codes", tags=["管理后台-邀请码"])


@router.post("", status_code=201)
async def create_invite_code(
    req: CreateInviteCodeRequest,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """生成限时邀请码。"""
    expires_at = datetime.now(timezone.utc) + timedelta(hours=req.duration_hours)
    invite = InviteCode(
        code=InviteCode.generate_code(),
        max_uses=req.max_uses,
        expires_at=expires_at,
        created_by=current_user.id,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    logger.info(f"限时邀请码已生成: id={invite.id}, by={current_user.username}, duration={req.duration_hours}h")
    return {
        "id": invite.id,
        "code": invite.code,
        "max_uses": invite.max_uses,
        "use_count": invite.use_count,
        "expires_at": invite.expires_at.isoformat(),
        "is_active": invite.is_active,
        "created_at": invite.created_at.isoformat(),
    }


@router.get("", response_model=InviteCodeListResponse)
async def list_invite_codes(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """列出活跃的限时邀请码（最多 5 条）。"""
    result = await db.execute(
        select(InviteCode)
        .where(InviteCode.is_active == True)
        .order_by(InviteCode.created_at.desc())
        .limit(5)
    )
    codes = result.scalars().all()
    return {"items": [
        InviteCodeItem(
            id=c.id,
            code=c.code,
            max_uses=c.max_uses,
            use_count=c.use_count,
            expires_at=c.expires_at,
            is_active=c.is_active,
            created_at=c.created_at,
        )
        for c in codes
    ]}


@router.delete("/{invite_id}", status_code=204)
async def deactivate_invite_code(
    invite_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """停用限时邀请码（软删除）。"""
    result = await db.execute(select(InviteCode).where(InviteCode.id == invite_id))
    invite = result.scalar_one_or_none()
    if not invite:
        raise NotFoundException("邀请码不存在")
    invite.is_active = False
    await db.commit()
    logger.info(f"限时邀请码已停用: id={invite_id}, by={current_user.username}")
    return None
