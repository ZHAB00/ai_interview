"""Unified logging configuration with request_id injection."""

import json
import logging
import os
import sys
from contextvars import ContextVar
from typing import Any

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
session_id_ctx: ContextVar[str] = ContextVar("session_id", default="-")


def truncate(text: str, max_len: int = 200) -> str:
    """Truncate text, appending '...' if it exceeds max_len."""
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


class PlainFormatter(logging.Formatter):
    """Human-readable console log formatter.

    Format: 2026-04-27 17:09:11 [INFO] module.name: message  [req=xxx session=yyy]
    Request ID and session ID are only shown when set to non-default values.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.datefmt = "%Y-%m-%d %H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id_ctx.get()
        record.session_id = session_id_ctx.get()
        ts = self.formatTime(record, self.datefmt)
        base = f"{ts} [{record.levelname}] {record.name}: {record.getMessage()}"

        extras = []
        if record.request_id and record.request_id != "-":
            extras.append(f"req={record.request_id}")
        if record.session_id and record.session_id != "-":
            extras.append(f"session={record.session_id}")
        if extras:
            base += "  [" + " ".join(extras) + "]"

        if record.exc_info and record.exc_info[0]:
            base += "\n" + self.formatException(record.exc_info)
        return base


class JSONFormatter(logging.Formatter):
    """JSON log formatter that injects request_id and session_id."""

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id_ctx.get()
        record.session_id = session_id_ctx.get()
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "request_id": record.request_id,
            "session_id": record.session_id,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def configure_module_levels(app_settings: Any) -> None:
    """Apply per-module log level overrides from Settings."""
    overrides = {
        "app": app_settings.LOG_LEVEL_APP,
        "app.access": app_settings.LOG_LEVEL_ACCESS,
        "watchfiles": app_settings.LOG_LEVEL_WATCHFILES,
        "uvicorn": app_settings.LOG_LEVEL_UVCORN,
        "httpx": app_settings.LOG_LEVEL_HTTPX,
    }
    for module_name, level_str in overrides.items():
        if level_str:
            level = getattr(logging, level_str.upper(), None)
            if level is not None:
                logging.getLogger(module_name).setLevel(level)

    # Hard-coded noise suppression
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)


def logging_setup(level: int = logging.INFO, fmt: str = "plain") -> None:
    """Initialize the root logger.

    Args:
        level: Root log level (e.g. logging.INFO).
        fmt: "plain" for human-readable or "json" for structured output.
    """
    formatter = JSONFormatter() if fmt == "json" else PlainFormatter()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Default noise suppression
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)

    # Apply per-module overrides from .env
    try:
        from app.core.config import settings

        configure_module_levels(settings)
    except Exception:
        pass


def suppress_startup_duplicate() -> None:
    """Suppress duplicate startup log in uvicorn reload child process.

    Call once in create_app() to prevent the second '应用启动完成' message.
    """
    os.environ.setdefault("_APP_STARTUP_LOGGED", "0")
