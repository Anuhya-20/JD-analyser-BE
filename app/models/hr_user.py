import uuid
import enum
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Boolean, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin


class HRUser(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "hr_users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Forgot-password fields
    password_reset_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_reset_expires: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    interview_sessions: Mapped[list["InterviewSession"]] = relationship(
        "InterviewSession", back_populates="generated_by"
    )

    def __repr__(self) -> str:
        return f"<HRUser email={self.email!r}>"
