"""SMS captcha service: send and verify phone verification codes.

Uses Redis for storage — works correctly across multiple workers.
"""

import json
import logging
import random
import re
import string
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)


def clean_phone(phone: str) -> str:
    """Remove non-digit chars and strip China country code prefix."""
    cleaned = re.sub(r"\D", "", phone)
    if cleaned.startswith("86") and len(cleaned) > 11:
        cleaned = cleaned[2:]
    elif cleaned.startswith("86"):
        cleaned = cleaned[2:] if len(cleaned) > 11 else cleaned
    return cleaned


def is_valid_china_phone(phone: str) -> bool:
    """Check if the cleaned phone number is a valid China mobile number."""
    return len(phone) == 11 and phone.startswith("1")


def _end_of_day_ttl() -> int:
    """Seconds until the end of today (UTC)."""
    now = datetime.now(timezone.utc)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return int((end - now).total_seconds()) + 2


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


class CaptchaService:
    """Redis-backed SMS captcha service.

    Key layout (all keys have TTL so no manual cleanup needed):
      captcha:{captcha_id}         — JSON: code, phone, type, attempts
      captcha:cooldown:{phone}:{t} — SETNX TTL = retry_seconds
      captcha:daily:{phone}:{date} — INCR counter, EXPIREAT end of day
    """

    def __init__(self):
        self._redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    # ── send ──────────────────────────────────────────────

    async def send(self, phone: str, captcha_type: str) -> dict[str, Any]:
        """Generate and send an SMS captcha. Returns {captcha_id, expires_in, retry_after}."""
        raw_phone = phone
        phone = clean_phone(phone)
        if not is_valid_china_phone(phone):
            raise ValueError("手机号格式无效")

        r = await self._get_redis()

        # Rate limit: 60-second cooldown (atomic SETNX)
        cooldown_key = f"captcha:cooldown:{phone}:{captcha_type}"
        acquired = await r.set(cooldown_key, "1", nx=True, ex=settings.ALIYUN_SMS_RETRY_SECONDS)
        if not acquired:
            ttl = await r.ttl(cooldown_key)
            raise RuntimeError(f"请{max(1, ttl)}秒后再试")

        # Daily limit (IRR counter, TTL to end of day)
        daily_key = f"captcha:daily:{phone}:{_today_str()}"
        today_count = await r.incr(daily_key)
        if today_count == 1:
            await r.expire(daily_key, _end_of_day_ttl())
        if today_count > settings.ALIYUN_SMS_MAX_DAILY:
            raise RuntimeError("今日短信发送次数已用完")

        # Generate code
        code = "".join(random.choice(string.digits) for _ in range(settings.ALIYUN_SMS_CODE_LENGTH))
        captcha_id = str(uuid.uuid4())

        # Store in Redis
        data = json.dumps({
            "phone": phone,
            "code": code,
            "type": captcha_type,
            "attempts": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await r.setex(f"captcha:{captcha_id}", settings.ALIYUN_SMS_VALID_SECONDS, data)

        # Send via Aliyun SMS — if not configured, log the code (dev mode)
        self._send_sms(raw_phone, code, captcha_type)

        logger.info(f"SMS captcha sent: phone={phone}, type={captcha_type}")
        return {
            "captcha_id": captcha_id,
            "phone": phone,
            "expires_in": settings.ALIYUN_SMS_VALID_SECONDS,
            "retry_after": settings.ALIYUN_SMS_RETRY_SECONDS,
        }

    def _send_sms(self, phone: str, code: str, captcha_type: str) -> None:
        """Send SMS via Alibaba Cloud. Falls back to console log in dev mode."""
        template = {
            "register": settings.ALIYUN_SMS_TEMPLATE_REGISTER,
            "login": settings.ALIYUN_SMS_TEMPLATE_LOGIN,
            "reset_password": settings.ALIYUN_SMS_TEMPLATE_RESET_PASSWORD,
        }.get(captcha_type, "")

        sign = settings.ALIYUN_SMS_SIGN_NAME

        if not template or not sign:
            logger.info(f"[DEV] SMS captcha: phone={phone}, code={code}, type={captcha_type}")
            return

        if not settings.ALIYUN_ACCESS_KEY_ID or not settings.ALIYUN_ACCESS_KEY_SECRET:
            logger.info(f"[DEV] SMS captcha: phone={phone}, code={code}, type={captcha_type}")
            return

        try:
            from alibabacloud_tea_openapi import models as open_api_models

            config = open_api_models.Config(
                access_key_id=settings.ALIYUN_ACCESS_KEY_ID,
                access_key_secret=settings.ALIYUN_ACCESS_KEY_SECRET,
                region_id="cn-hangzhou",
            )

            template_param = f'{{"code":"{code}","min":"5"}}'

            if template.isdigit():
                from alibabacloud_dypnsapi20170525.client import Client as DypnsapiClient
                from alibabacloud_dypnsapi20170525 import models as dypnsapi_models

                config.endpoint = "dypnsapi.aliyuncs.com"
                client = DypnsapiClient(config)

                req = dypnsapi_models.SendSmsVerifyCodeRequest(
                    phone_number=phone,
                    sign_name=sign,
                    template_code=template,
                    template_param=template_param,
                )
                from alibabacloud_tea_util import models as util_models
                runtime = util_models.RuntimeOptions()
                response = client.send_sms_verify_code_with_options(req, runtime)
                if response.body.code != "OK":
                    raise RuntimeError(f"SMS send failed: {response.body.message}")
                logger.info(f"SMS sent (dypnsapi): phone={phone}")

            else:
                from alibabacloud_dysmsapi20170525.client import Client as DysmsapiClient
                from alibabacloud_dysmsapi20170525 import models as dysmsapi_models

                config.endpoint = "dysmsapi.aliyuncs.com"
                client = DysmsapiClient(config)

                req = dysmsapi_models.SendSmsRequest(
                    phone_numbers=phone,
                    sign_name=sign,
                    template_code=template,
                    template_param=template_param,
                )
                from alibabacloud_tea_util import models as util_models
                runtime = util_models.RuntimeOptions()
                response = client.send_sms_with_options(req, runtime)
                if response.body.code != "OK":
                    raise RuntimeError(f"SMS send failed: {response.body.message}")
                logger.info(f"SMS sent (dysmsapi): phone={phone}, biz_id={response.body.biz_id}")

        except ImportError:
            logger.info(f"[DEV] SMS SDK not installed, code: {code} for {phone}")
        except Exception as e:
            logger.error(f"SMS send error: {e}")
            raise RuntimeError("短信发送失败，请稍后重试")

    # ── verify ────────────────────────────────────────────

    async def verify(self, phone: str, code: str, captcha_type: str) -> tuple[bool, str, str | None]:
        """Verify a captcha code. Returns (ok, message, token).

        On success, returns a temporary token for the registration/reset flow.
        Expired captchas are automatically removed by Redis TTL — no manual cleanup.
        """
        phone = clean_phone(phone)
        r = await self._get_redis()

        # Scan for unverified captcha for this phone+type (keys are short-lived, safe to scan)
        pattern = f"captcha:*"
        cursor = 0
        matches: list[tuple[str, dict]] = []
        while True:
            cursor, keys = await r.scan(cursor, match=pattern, count=20)
            for key in keys:
                raw = await r.get(key)
                if not raw:
                    continue
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict) and item.get("phone") == phone and item.get("type") == captcha_type:
                    matches.append((key, item))
            if cursor == 0:
                break

        if not matches:
            return False, "验证码不存在或已过期，请重新发送", None

        matches.sort(key=lambda x: x[1].get("created_at", ""), reverse=True)
        captcha_key, item = matches[0]

        # Attempt limit
        if item.get("attempts", 0) >= 3:
            await r.delete(captcha_key)
            return False, "验证码尝试次数过多，请重新发送", None

        item["attempts"] = item.get("attempts", 0) + 1
        # Refresh the stored record with updated attempts
        remaining_ttl = await r.ttl(captcha_key)
        if remaining_ttl <= 0:
            remaining_ttl = settings.ALIYUN_SMS_VALID_SECONDS
        await r.setex(captcha_key, remaining_ttl, json.dumps(item, ensure_ascii=False))

        if item["code"] != code.strip():
            return False, "验证码错误", None

        # Clean up on success
        await r.delete(captcha_key)

        # Generate temp token (10 min TTL)
        from app.core.security import create_access_token
        token = create_access_token(
            data={"phone": phone, "captcha_id": captcha_key.removeprefix("captcha:"), "purpose": captcha_type},
            expires_delta=10,
        )
        return True, "验证成功", token


# Singleton
captcha_service = CaptchaService()
