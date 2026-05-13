"""JWT token handling, password hashing, invite codes, and token revocation."""

import hashlib
import hmac as hmac_lib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as redis
import jwt
from jwt import PyJWTError as JWTError
from passlib.context import CryptContext

from app.core.config import settings

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_revoke_redis: redis.Redis | None = None


async def _get_revoke_redis() -> redis.Redis:
    global _revoke_redis
    if _revoke_redis is None:
        _revoke_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _revoke_redis


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict[str, Any], expires_delta: int | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_delta or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.setdefault("type", "access")
    to_encode.setdefault("jti", uuid.uuid4().hex)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict[str, Any], expires_delta: int | None = None) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_delta or settings.REFRESH_TOKEN_EXPIRE_MINUTES
    )
    to_encode.setdefault("type", "refresh")
    to_encode.setdefault("jti", uuid.uuid4().hex)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token. Raises JWTError on failure."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# ---- Invite Code (15-minute rotation via time-based HMAC) ----

_INVITE_WINDOW_MINUTES = 15
_INVITE_CODE_LENGTH = 12


def _get_current_window() -> str:
    """Return a unique string for the current 15-minute time window."""
    now = datetime.now(timezone.utc)
    quarter = now.minute // _INVITE_WINDOW_MINUTES
    return now.strftime(f"%Y%m%d-%H-{quarter:02d}")


def _get_prev_window(window: str) -> str:
    """Return the previous 15-minute window string (for grace period)."""
    # Parse YYYYMMDD-HH-QQ format, go back one quarter
    date_part, hour, quarter = window.split("-")
    q = int(quarter)
    if q > 0:
        return f"{date_part}-{hour}-{q - 1:02d}"
    h = int(hour)
    if h > 0:
        return f"{date_part}-{h - 1:02d}-3"
    # Midnight rollback: simplest approach — just return empty
    return ""


def generate_invite_code() -> str:
    """Generate a time-based invite code valid for this 15-minute window."""
    window = _get_current_window()
    digest = hmac_lib.new(
        settings.SECRET_KEY.encode("utf-8"),
        window.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:_INVITE_CODE_LENGTH].upper()


def validate_invite_code(code: str) -> bool:
    """Check if the invite code is valid for the current or previous window."""
    if not code or len(code) < 4:
        return False
    code = code.strip().upper()

    # Current window
    if code == generate_invite_code():
        return True

    # Previous window (15-min grace period)
    prev_window = _get_prev_window(_get_current_window())
    if prev_window:
        digest = hmac_lib.new(
            settings.SECRET_KEY.encode("utf-8"),
            prev_window.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if code == digest[:_INVITE_CODE_LENGTH].upper():
            return True

    return False


# ---- File download tokens (for authenticated /uploads/* access) ----

_FILE_TOKEN_EXPIRE_DAYS = 7


def create_file_token(user_id: int, filename: str) -> str:
    """Create a JWT for authenticated file download. 7-day TTL for report playback."""
    expire = datetime.now(timezone.utc) + timedelta(days=_FILE_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(user_id), "file": filename, "type": "file_access", "jti": uuid.uuid4().hex, "exp": expire},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


# ---- Token Revocation (Redis-backed blacklist) ----


async def revoke_token(jti: str, exp_timestamp: float) -> None:
    """Revoke a JWT by its jti. Auto-expires when the token would have expired."""
    ttl = max(1, int(exp_timestamp - datetime.now(timezone.utc).timestamp()))
    try:
        r = await _get_revoke_redis()
        await r.setex(f"revoked:{jti}", ttl, "1")
        logger.info(f"Token revoked: jti={jti[:8]}..., ttl={ttl}s")
    except Exception as e:
        logger.warning(f"Failed to revoke token (Redis error): {e}")


async def is_token_revoked(jti: str | None) -> bool:
    """Check if a JWT has been revoked. Returns False if jti is None (legacy tokens)."""
    if not jti:
        return False
    try:
        r = await _get_revoke_redis()
        return await r.exists(f"revoked:{jti}") == 1
    except Exception as e:
        logger.warning(f"Failed to check token revocation (Redis error): {e}")
        return False  # Fail open on Redis errors — don't lock users out


async def validate_db_invite_code(code: str, db) -> bool:
    """Check if the code matches an active time-limited invite code in the DB.
    Increments use_count on match. Returns False if not found or expired/fully used.
    """
    from sqlalchemy import select
    from app.models.invite_code import InviteCode
    from datetime import datetime, timezone

    code = code.strip().upper()
    result = await db.execute(
        select(InviteCode).where(
            InviteCode.code == code,
            InviteCode.is_active == True,
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        return False

    if invite.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return False

    if invite.max_uses is not None and invite.use_count >= invite.max_uses:
        return False

    invite.use_count += 1
    await db.commit()
    logger.info(f"DB邀请码使用: id={invite.id}, code={code}, use_count={invite.use_count}")
    return True
