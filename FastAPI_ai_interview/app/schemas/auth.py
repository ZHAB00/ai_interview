"""Auth-related Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\d{11}$", description="手机号，11位数字")
    username: str = Field(..., min_length=2, max_length=30, description="用户名")
    password: str = Field(..., min_length=8, max_length=128, description="密码，至少8位，含英文和数字")
    invite_code: str = Field(..., min_length=4, max_length=32, description="内测邀请码")
    sms_token: str = Field(..., min_length=10, description="短信验证通过后获取的临时令牌")


class RegisterResponse(BaseModel):
    user_id: int
    phone: str
    username: str
    role: str
    created_at: datetime


class LoginRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\d{11}$")
    password: str = Field(..., min_length=6)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user_id: int
    username: str
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ResetPasswordRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\d{11}$", description="手机号")
    sms_token: str = Field(..., min_length=10, description="短信验证通过后获取的临时令牌")
    new_password: str = Field(..., min_length=8, max_length=128, description="新密码，至少8位，含英文和数字")


class TokenData(BaseModel):
    user_id: int | None = None
    role: str | None = None
