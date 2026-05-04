"""SQLAlchemy models - import all models so Alembic can discover them."""

from app.core.database import Base
from app.models.user import User
from app.models.resume import Resume
from app.models.interview import Interview
from app.models.question import Question
from app.models.document import Document
from app.models.report import Report
from app.models.feedback import Feedback
from app.models.message import Message

__all__ = ["Base", "User", "Resume", "Interview", "Question", "Document", "Report", "Feedback", "Message"]
