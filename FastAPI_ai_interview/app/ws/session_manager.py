"""WebSocket session state management via Redis Hash.

Stores per-interview session state for reconnection and monitoring.
Key: interview:{interview_id}:state
Fields: stage, questions_asked, last_active, status
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)

SESSION_TTL = 900  # 15 minutes


class SessionManager:
    """Manages WebSocket interview session state in Redis.

    Provides structured state storage per interview session, enabling
    reconnection within the TTL window and progress monitoring.
    """

    def __init__(self):
        self.redis: redis.Redis | None = None
        self._connect_attempted = False

    async def _ensure_connection(self):
        if self.redis is not None:
            return
        if self._connect_attempted:
            return
        self._connect_attempted = True
        try:
            self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            await self.redis.ping()
            logger.info("Redis 会话管理已连接")
        except Exception as e:
            logger.warning(f"Redis 不可用，会话状态将仅存于内存: {e}")
            self.redis = None

    def _key(self, interview_id: int) -> str:
        return f"interview:{interview_id}:state"

    def _token_key(self, token: str) -> str:
        return f"ws_token:{token}"

    async def create_session(self, interview_id: int, state: dict[str, Any]) -> None:
        """Initialize a new session state in Redis."""
        await self._ensure_connection()
        data = {
            "stage": state.get("stage", ""),
            "questions_asked": json.dumps(state.get("questions_asked", [])),
            "chat_history_summary": json.dumps(state.get("chat_history_summary", [])),
            "last_active": datetime.now(timezone.utc).isoformat(),
            "status": state.get("status", "in_progress"),
        }
        if self.redis:
            for k, v in data.items():
                await self.redis.hset(self._key(interview_id), k, v)
            await self.redis.expire(self._key(interview_id), SESSION_TTL)
        logger.info(f"会话创建: interview_id={interview_id}")

    async def update_session(self, interview_id: int, updates: dict[str, Any]) -> None:
        """Update session state fields."""
        await self._ensure_connection()
        updates["last_active"] = datetime.now(timezone.utc).isoformat()
        if self.redis:
            for k, v in updates.items():
                await self.redis.hset(self._key(interview_id), k, v)
            await self.redis.expire(self._key(interview_id), SESSION_TTL)

    async def get_session(self, interview_id: int) -> dict[str, Any] | None:
        """Retrieve session state, or None if expired or unavailable."""
        await self._ensure_connection()
        if not self.redis:
            return None
        data = await self.redis.hgetall(self._key(interview_id))
        if not data:
            return None
        return {
            "stage": data.get("stage", ""),
            "questions_asked": json.loads(data.get("questions_asked", "[]")),
            "chat_history_summary": json.loads(data.get("chat_history_summary", "[]")),
            "last_active": data.get("last_active", ""),
            "status": data.get("status", ""),
        }

    async def delete_session(self, interview_id: int) -> None:
        """Remove session state (interview completed/expired)."""
        await self._ensure_connection()
        if self.redis:
            await self.redis.delete(self._key(interview_id))
        logger.info(f"会话已删除: interview_id={interview_id}")

    async def store_token(self, token: str, interview_id: int, ttl: int = 300) -> None:
        """Store WebSocket token → interview_id mapping."""
        await self._ensure_connection()
        if self.redis:
            await self.redis.setex(self._token_key(token), ttl, interview_id)
        logger.info(f"Token已存储: interview_id={interview_id}")

    async def validate_token(self, token: str) -> int | None:
        """Validate ws_token and return interview_id, or None if invalid/expired."""
        await self._ensure_connection()
        if not self.redis:
            # Without Redis, token validation is done via interview record
            return None
        val = await self.redis.get(self._token_key(token))
        return int(val) if val else None

    async def heartbeat(self, interview_id: int) -> None:
        """Update last_active timestamp."""
        await self._ensure_connection()
        if self.redis:
            key = self._key(interview_id)
            await self.redis.hset(
                key, "last_active", datetime.now(timezone.utc).isoformat()
            )
            await self.redis.expire(key, SESSION_TTL)

    async def extend_token_ttl(self, token: str, ttl: int = 900) -> None:
        """Extend ws_token TTL after successful connection for reconnection support."""
        await self._ensure_connection()
        if self.redis:
            await self.redis.expire(self._token_key(token), ttl)
            logger.info(f"Token TTL已延长: ttl={ttl}s")

    async def can_reconnect(self, interview_id: int, token: str) -> bool:
        """Check if reconnection is allowed: token valid + interview in_progress."""
        await self._ensure_connection()
        if not self.redis:
            return False

        # Token must be mapped to this interview
        redis_id = await self.validate_token(token)
        if redis_id != interview_id:
            return False

        # Session must still exist and be in progress
        session = await self.get_session(interview_id)
        if not session:
            return False

        if session.get("status") != "in_progress":
            return False

        return True

    async def restore_session(self, interview_id: int) -> dict | None:
        """Get session state for reconnection recovery."""
        await self._ensure_connection()
        if not self.redis:
            return None

        session = await self.get_session(interview_id)
        if not session:
            return None

        return {
            "stage": session.get("stage", ""),
            "questions_asked": session.get("questions_asked", []),
            "chat_history_summary": session.get("chat_history_summary", []),
            "status": session.get("status", "in_progress"),
        }

    async def list_active_interview_ids(self) -> list[int]:
        """Return all interview IDs that currently have active WS session state."""
        await self._ensure_connection()
        if not self.redis:
            return []
        ids = []
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor, match="interview:*:state", count=100
            )
            for key in keys:
                try:
                    ids.append(int(key.split(":")[1]))
                except (ValueError, IndexError):
                    pass
            if cursor == 0:
                break
        return ids

    @property
    def is_available(self) -> bool:
        """Check if Redis session manager is available."""
        return self.redis is not None


# Global singleton
session_manager = SessionManager()
