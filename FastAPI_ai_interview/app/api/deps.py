"""FastAPI dependency injection: database sessions and current user."""

import logging
from datetime import datetime, timezone

from fastapi import Depends, Header
from jwt import PyJWTError as JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import UnauthorizedException
from app.core.security import decode_token, is_token_revoked
from app.models.user import User

logger = logging.getLogger(__name__)


async def get_current_user(
    authorization: str = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency: extract and validate the current user from the JWT token."""
    if not authorization:
        raise UnauthorizedException(message="缺少 Authorization 请求头")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedException(message="Authorization 格式错误，应为 Bearer <token>")

    try:
        payload = decode_token(token)
        user_id: int | None = payload.get("user_id")
        token_type: str | None = payload.get("type")
        if user_id is None or token_type != "access":
            raise UnauthorizedException(message="Token 无效或不是 access token")
        jti: str | None = payload.get("jti")
    except JWTError:
        raise UnauthorizedException(message="Token 解析失败")

    # Check revocation
    if await is_token_revoked(jti):
        raise UnauthorizedException(message="Token 已被吊销，请重新登录")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedException(message="用户不存在")
    if user.is_disabled:
        raise UnauthorizedException(message="账号已被禁用")

    # Update last_active_at for online status tracking (admin monitor)
    # Throttle: only write if last update was > 30s ago
    now = datetime.now(timezone.utc)
    if user.last_active_at is None or (now - user.last_active_at.replace(tzinfo=timezone.utc)).total_seconds() > 30:
        user.last_active_at = now
        await db.commit()

    return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency: ensure the current user is an admin."""
    if current_user.role != "admin":
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException(message="需要管理员权限")
    return current_user
