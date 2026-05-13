"""Authentication endpoints: register, login, refresh token, reset password."""

import logging
import re

from fastapi import APIRouter, Depends, Header
from jwt import PyJWTError as JwtError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user, get_db
from app.core.exceptions import ConflictException, UnauthorizedException, ValidationErrorException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_invite_code,
    hash_password,
    revoke_token,
    validate_db_invite_code,
    validate_invite_code,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["认证"])


def _validate_password_strength(password: str) -> None:
    """Password must be 8+ chars with both letters and digits."""
    if len(password) < 8:
        raise ValidationErrorException("密码长度至少8位")
    if not re.search(r"[a-zA-Z]", password):
        raise ValidationErrorException("密码必须包含英文字母")
    if not re.search(r"\d", password):
        raise ValidationErrorException("密码必须包含数字")


def _verify_sms_token(token: str, phone: str, purpose: str) -> bool:
    """Verify the SMS temp token matches the phone and purpose."""
    try:
        payload = decode_token(token)
        return payload.get("phone") == phone and payload.get("purpose") == purpose
    except Exception:
        return False


@router.get("/invite-code")
async def get_invite_code(
    current_user = Depends(get_current_admin),
):
    """获取当前15分钟有效的内测邀请码（仅管理员）。"""
    code = generate_invite_code()
    logger.info(f"管理员 {current_user.username} 获取了邀请码")
    return {"invite_code": code, "valid_minutes": 15, "note": "同一窗口内的上一个码也有效（15分钟容错）"}


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """用户注册：邀请码 + 短信验证码 + 强密码。"""
    # Step 1: Check phone
    result = await db.execute(select(User).where(User.phone == req.phone))
    if result.scalar_one_or_none():
        raise ConflictException("手机号已注册")

    # Step 2: Validate invite code — DB timed codes authoritative, HMAC as fallback
    db_result = await validate_db_invite_code(req.invite_code, db)
    if db_result is True:
        pass  # Valid timed code, use_count already incremented
    elif db_result is False:
        raise ValidationErrorException("邀请码不正确")  # Found in DB but invalid
    elif not validate_invite_code(req.invite_code):
        raise ValidationErrorException("邀请码不正确")  # Not in DB, not HMAC

    # Step 3: Verify SMS token
    if not _verify_sms_token(req.sms_token, req.phone, "register"):
        raise ValidationErrorException("短信验证未通过，请重新验证")

    # Step 4: Validate password strength
    _validate_password_strength(req.password)

    # Step 5: Validate username
    if len(req.username) < 2 or len(req.username) > 30:
        raise ValidationErrorException("用户名长度需在2-30个字符之间")

    user = User(
        phone=req.phone,
        username=req.username,
        password_hash=hash_password(req.password),
        role="candidate",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(f"新用户注册: user_id={user.id}, phone={req.phone}")
    return RegisterResponse(
        user_id=user.id,
        phone=user.phone,
        username=user.username,
        role=user.role,
        created_at=user.created_at,
    )


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录：手机号+密码，返回 JWT 令牌对。"""
    result = await db.execute(select(User).where(User.phone == req.phone))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise UnauthorizedException("账号或密码错误")

    access_token = create_access_token(
        data={"user_id": user.id, "role": user.role}
    )
    refresh_token = create_refresh_token(
        data={"user_id": user.id, "role": user.role}
    )

    logger.info(f"用户登录: user_id={user.id}")
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=1440 * 60,  # 24h in seconds
        user_id=user.id,
        username=user.username,
        role=user.role,
    )


@router.post("/logout", status_code=204)
async def logout(authorization: str = Header(default=None)):
    """用户登出。吊销当前 access token，使其立即失效。"""
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            try:
                payload = decode_token(token)
                jti = payload.get("jti")
                exp = payload.get("exp")
                if jti and exp:
                    await revoke_token(jti, exp)
            except JwtError:
                pass  # Invalid token — nothing to revoke
    return None


@router.post("/refresh", response_model=LoginResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """刷新令牌：使用 refresh_token 获取新的令牌对。"""
    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise UnauthorizedException("Token 类型不是 refresh token")
        user_id = payload.get("user_id")
    except Exception:
        raise UnauthorizedException("Token 无效或过期")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedException("用户不存在")

    new_access = create_access_token(data={"user_id": user.id, "role": user.role})
    new_refresh = create_refresh_token(data={"user_id": user.id, "role": user.role})

    # Revoke the old refresh token so it cannot be reused
    old_jti = payload.get("jti")
    old_exp = payload.get("exp")
    if old_jti and old_exp:
        await revoke_token(old_jti, old_exp)

    return LoginResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=1440 * 60,
        user_id=user.id,
        username=user.username,
        role=user.role,
    )


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """重置密码：通过短信验证码验证身份后设置新密码。"""
    # Verify SMS token
    if not _verify_sms_token(req.sms_token, req.phone, "reset_password"):
        raise ValidationErrorException("短信验证未通过，请重新验证")

    # Validate new password
    _validate_password_strength(req.new_password)

    # Find user
    result = await db.execute(select(User).where(User.phone == req.phone))
    user = result.scalar_one_or_none()
    if not user:
        raise ValidationErrorException("用户不存在")

    user.password_hash = hash_password(req.new_password)
    await db.commit()

    logger.info(f"密码重置成功: phone={req.phone}")
    return {"success": True, "message": "密码重置成功，请重新登录"}
