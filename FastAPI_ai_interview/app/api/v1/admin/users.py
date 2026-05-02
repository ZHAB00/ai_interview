"""Admin user management endpoints."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.models.user import User
from app.schemas.admin import AdminUserItem, AdminUserListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/users", tags=["管理后台-用户管理"])


@router.get("", response_model=AdminUserListResponse)
async def list_users(
    page: int = 1,
    page_size: int = 20,
    role: str | None = None,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """查询用户列表。"""
    page_size = min(page_size, 100)
    query = select(User)
    count_query = select(func.count()).select_from(User)

    if role:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(
        query.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    users = result.scalars().all()

    items = [
        AdminUserItem(
            id=u.id,
            phone=u.phone,
            username=u.username,
            role=u.role,
            created_at=u.created_at,
        )
        for u in users
    ]

    return AdminUserListResponse(items=items, total=total, page=page, page_size=page_size)


@router.put("/{user_id}/disable")
async def disable_user(
    user_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """禁用或启用用户（切换 disabled 状态）。"""
    from fastapi import HTTPException

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")

    # Toggle: if currently active, disable; if disabled, enable
    current_status = getattr(user, "is_disabled", False)
    user.is_disabled = not current_status

    await db.commit()
    action = "禁用" if user.is_disabled else "启用"
    logger.info(f"用户{action}: user_id={user_id}, is_disabled={user.is_disabled}")
    return {"message": f"用户已{action}", "user_id": user_id, "is_disabled": user.is_disabled}
