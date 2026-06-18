import uuid
import enum
from typing import Optional
from sqlalchemy import Text, ForeignKey, JSON, Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin


class RecommendationLevel(str, enum.Enum):
    STRONGLY_RECOMMENDED = "strongly_recommended"
    RECOMMENDED = "recommended"
    MAYBE = "maybe"
    NOT_RECOMMENDED = "not_recommended"


class Recommendation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "recommendations"

    match_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("match_results.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    level: Mapped[RecommendationLevel] = mapped_column(
        SAEnum(RecommendationLevel, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    recruiter_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    interview_questions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    suggested_interview_stages: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    red_flags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    highlight_points: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    culture_fit_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship
    match_result: Mapped["MatchResult"] = relationship(
        "MatchResult", back_populates="recommendation"
    )

    def __repr__(self) -> str:
        return f"<Recommendation id={self.id} level={self.level}>"
