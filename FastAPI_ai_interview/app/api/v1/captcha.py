"""SMS captcha endpoints: send and verify phone codes."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import ValidationErrorException, ConflictException
from app.models.user import User
from app.services.captcha_service import captcha_service, clean_phone, is_valid_china_phone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/captcha", tags=["短信验证码"])


class SendSmsRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20, description="手机号")
    captcha_type: str = Field(default="register", description="验证码类型: register / login / reset_password")


class VerifySmsRequest(BaseModel):
    phone: str = Field(..., description="手机号")
    code: str = Field(..., min_length=4, max_length=10, description="短信验证码")
    captcha_type: str = Field(default="register", description="验证码类型")


@router.post("/send")
async def send_sms(req: SendSmsRequest, db: AsyncSession = Depends(get_db)):
    """发送短信验证码。"""
    phone = clean_phone(req.phone)
    if not is_valid_china_phone(phone):
        raise ValidationErrorException("手机号格式无效")

    # Register flow: check if already registered
    if req.captcha_type == "register":
        result = await db.execute(select(User).where(User.phone == phone))
        if result.scalar_one_or_none():
            raise ConflictException("手机号已注册")

    # Reset password flow: check phone exists
    if req.captcha_type == "reset_password":
        result = await db.execute(select(User).where(User.phone == phone))
        if not result.scalar_one_or_none():
            raise ValidationErrorException("该手机号未注册")

    try:
        data = await captcha_service.send(req.phone, req.captcha_type)
        return {"success": True, "data": data}
    except ValueError as e:
        raise ValidationErrorException(str(e))
    except RuntimeError as e:
        raise ValidationErrorException(str(e))


@router.post("/verify")
async def verify_sms(req: VerifySmsRequest):
    """验证短信验证码，返回临时令牌。"""
    try:
        ok, message, token = await captcha_service.verify(req.phone, req.code, req.captcha_type)
        return {
            "success": ok,
            "message": message,
            "token": token,
            "expires_in": 600 if token else None,
        }
    except ValueError as e:
        raise ValidationErrorException(str(e))
