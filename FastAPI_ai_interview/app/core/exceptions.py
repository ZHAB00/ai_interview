"""Custom exception classes and global exception handlers."""

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class AppException(HTTPException):
    """Base application exception with a custom error code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict | None = None,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.details = details


class NotFoundException(AppException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(status_code=404, code="NOT_FOUND", message=message)


class ConflictException(AppException):
    def __init__(self, message: str = "资源冲突"):
        super().__init__(status_code=409, code="CONFLICT", message=message)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "未登录或 token 无效"):
        super().__init__(status_code=401, code="UNAUTHORIZED", message=message)


class ForbiddenException(AppException):
    def __init__(self, message: str = "权限不足"):
        super().__init__(status_code=403, code="FORBIDDEN", message=message)


class FileTooLargeException(AppException):
    def __init__(self, message: str = "文件超过大小限制"):
        super().__init__(status_code=413, code="FILE_TOO_LARGE", message=message)


class ValidationErrorException(AppException):
    def __init__(self, message: str = "参数校验失败", details: dict | None = None):
        super().__init__(
            status_code=422, code="VALIDATION_ERROR", message=message, details=details
        )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Global handler for AppException."""
    content = {
        "error": {
            "code": exc.code,
            "message": exc.detail,
        }
    }
    if exc.details:
        content["error"]["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content=content)


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler for unhandled exceptions."""
    import logging
    logging.getLogger(__name__).exception(
        "Unhandled exception: %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误",
            }
        },
    )


# Map Pydantic English error messages to Chinese (case-insensitive matching)
import re

_VALIDATION_MSG_MAP = [
    ("field required", "此字段为必填"),
    ("string should have at least (\\d+) characters", r"字符串长度至少需要 \1 个字符"),
    ("ensure this value has at least (\\d+) items", r"至少需要 \1 项"),
    ("value is not a valid integer", "值不是有效的整数"),
    ("value is not a valid email address", "值不是有效的邮箱地址"),
    ("string does not match regex", "字符串格式不正确"),
    ("string should match pattern", "字符串格式不正确"),
    ("ensure this value has at most (\\d+) characters", r"字符串长度最多 \1 个字符"),
]


def _translate_validation_msg(msg: str) -> str:
    """Translate common Pydantic error messages to Chinese."""
    for pattern, replacement in _VALIDATION_MSG_MAP:
        msg = re.sub(pattern, replacement, msg, flags=re.IGNORECASE)
    return msg


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Normalize Pydantic validation errors to match the app error format (Chinese)."""
    messages = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err["loc"])
        msg = _translate_validation_msg(err["msg"])
        messages.append(f"{loc}: {msg}")
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "; ".join(messages),
            }
        },
    )


EXCEPTION_HANDLERS = {
    AppException: app_exception_handler,
    RequestValidationError: validation_exception_handler,
    Exception: generic_exception_handler,
}
