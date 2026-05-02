"""Middleware configuration: CORS, rate limiting, request ID injection, access logging."""

import json
import logging
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.logging_config import request_id_ctx, truncate

access_logger = logging.getLogger("app.access")


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the FastAPI application.

    CORS: Origins controlled by CORS_ORIGINS env var (comma-separated).
    Rate limiting: Enabled via RATE_LIMIT_ENABLED=true.
    CORS strict mode: Set CORS_STRICT=true in production to deny wildcard origins.
    """

    # ── CORS ──
    allow_origins = settings.CORS_ORIGINS_LIST
    if not allow_origins and not settings.DEBUG:
        allow_origins = []  # Production with no explicit origins: deny all

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    # ── Rate Limiting ──
    if settings.RATE_LIMIT_ENABLED:
        rate_limit = getattr(settings, "RATE_LIMIT", "60/minute")
        limiter = Limiter(key_func=get_remote_address, default_limits=[rate_limit])
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── Security headers middleware ──
    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # ── Request ID middleware ──
    @app.middleware("http")
    async def add_request_id(request, call_next):
        request_id = str(uuid.uuid4()).replace("-", "")[:16]
        request_id_ctx.set(request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # ── Access logging middleware (innermost, after request_id) ──
    @app.middleware("http")
    async def access_log(request: Request, call_next):
        start = time.time()

        # Determine which module/router handled this request
        module = _resolve_module(request)

        # Log incoming request (sanitize sensitive query params)
        qs = _safe_query_string(request)
        access_logger.info(
            "[%s] --> %s %s%s",
            module,
            request.method,
            request.url.path,
            qs,
        )

        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        # Capture & log response body (JSON/text only, truncated)
        body_display, response = await _capture_body(response)
        access_logger.info(
            "[%s] <-- %s %s%s (%d, %.0fms) %s",
            module,
            request.method,
            request.url.path,
            qs,
            response.status_code,
            duration_ms,
            body_display,
        )

        return response


def _resolve_module(request: Request) -> str:
    """Map request path to a friendly module name."""
    path = request.url.path
    if path.startswith("/api/auth"):
        return "auth"
    if path.startswith("/api/admin/questions"):
        return "admin:questions"
    if path.startswith("/api/admin/documents"):
        return "admin:documents"
    if path.startswith("/api/admin/users"):
        return "admin:users"
    if path.startswith("/api/admin"):
        return "admin"
    if path.startswith("/api/resumes"):
        return "resumes"
    if path.startswith("/api/interviews"):
        return "interviews"
    if path.startswith("/api/feedback"):
        return "feedback"
    if path.startswith("/ws/"):
        return "websocket"
    if path.startswith("/api/"):
        return "api"
    return "app"


def _safe_query_string(request: Request) -> str:
    """Build query string with sensitive params (token) redacted."""
    if not request.url.query:
        return ""
    query = request.url.query
    # Mask token param
    import re as _re
    query = _re.sub(r'(?<=[&?])token=[^&]*', 'token=***', query)
    return f"?{query}"


async def _capture_body(response: Response) -> tuple[str, Response]:
    """Read response body then return (display_str, rebuilt_response).

    Must rebuild the response because consuming body_iterator destroys the
    original async iterator. Returns a fresh Response so downstream
    middleware can still send the body to the client.
    """
    content_type = response.headers.get("content-type", "")

    # Don't consume binary or streaming responses
    if "application/json" not in content_type and "text/" not in content_type:
        return f"[{content_type or 'binary'}]", response

    body_bytes = b""
    async for chunk in response.body_iterator:
        body_bytes += chunk

    # Rebuild response — creating a fresh Response avoids Starlette
    # internals issues with re-initialising a live response object.
    new_response = Response(
        content=body_bytes,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
    )

    try:
        text = body_bytes.decode("utf-8")
        if "application/json" in content_type:
            try:
                obj = json.loads(text)
                text = json.dumps(obj, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
        return truncate(text, max_len=500), new_response
    except UnicodeDecodeError:
        return f"[{len(body_bytes)} bytes]", new_response
