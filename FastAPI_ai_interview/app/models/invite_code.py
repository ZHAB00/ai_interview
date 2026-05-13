"""InviteCode model — time-limited join codes managed by admins."""

import secrets

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(32), unique=True, nullable=False, index=True)
    max_uses = Column(Integer, nullable=True)  # NULL = unlimited
    use_count = Column(Integer, default=0, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    creator = relationship("User", lazy="selectin")

    @staticmethod
    def generate_code() -> str:
        return secrets.token_hex(6).upper()
