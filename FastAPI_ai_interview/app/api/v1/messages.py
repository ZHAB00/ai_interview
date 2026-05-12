"""Message board endpoints."""

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import ValidationErrorException
from app.models.message import Message
from app.models.user import User

DAILY_LIMIT = 3

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/messages", tags=["留言板"])

BAD_WORDS = [
    "fuck", "shit", "damn", "asshole", "bitch", "bastard",
    "操", "傻逼", "sb", "尼玛", "你妈", "妈的", "脑残", "弱智",
    "废物", "垃圾", "去死", "滚", "艹", "cnm", "fxxk",
]


def _filter_bad_words(text: str) -> str:
    result = text
    for w in BAD_WORDS:
        result = re.sub(w, "*" * len(w), result, flags=re.IGNORECASE)
    return result


def _has_bad_words(text: str) -> bool:
    return _filter_bad_words(text) != text


class CreateMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100)


class MessageItem(BaseModel):
    id: int
    user_id: int
    username: str
    role: str = "user"
    content: str
    created_at: str


@router.get("")
async def list_messages(
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """获取留言列表。"""
    result = await db.execute(
        select(Message, User.role)
        .join(User, Message.user_id == User.id, isouter=True)
        .order_by(Message.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()
    return {
        "items": [
            MessageItem(
                id=m.id,
                user_id=m.user_id,
                username=m.username,
                role=role or "user",
                content=m.content,
                created_at=m.created_at.isoformat(),
            )
            for m, role in rows
        ],
        "total": len(rows),
    }


@router.post("", status_code=201)
async def create_message(
    req: CreateMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发表留言。"""
    content = req.content.strip()

    if _has_bad_words(content):
        raise ValidationErrorException("留言包含不恰当词汇，请修改后重新提交")

    # Daily limit
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count()).select_from(Message).where(
            Message.user_id == current_user.id,
            Message.created_at >= today_start,
        )
    )
    count = result.scalar() or 0
    if count >= DAILY_LIMIT:
        raise ValidationErrorException(f"每天最多发送 {DAILY_LIMIT} 条留言")

    msg = Message(
        user_id=current_user.id,
        username=current_user.username,
        content=content,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    logger.info(f"新留言: user={current_user.username}, id={msg.id}")
    return {"id": msg.id, "username": msg.username, "content": msg.content, "created_at": msg.created_at.isoformat()}


@router.delete("/{message_id}")
async def delete_message(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除留言。作者可删自己的，管理员可删任意。"""
    result = await db.execute(select(Message).where(Message.id == message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        from app.core.exceptions import NotFoundException
        raise NotFoundException("留言不存在")
    if current_user.role != "admin" and msg.user_id != current_user.id:
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException("无权删除此留言")
    await db.delete(msg)
    await db.commit()
    logger.info(f"留言已删除: id={message_id}, by={current_user.username}")
    return {"detail": "ok"}
