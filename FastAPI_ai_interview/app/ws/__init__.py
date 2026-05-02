"""WebSocket real-time communication module."""

from app.ws.session_manager import session_manager
from app.ws.interview_ws import interview_handler

__all__ = ["session_manager", "interview_handler"]
