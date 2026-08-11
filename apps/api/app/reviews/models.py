import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.jobs.models import GenerationJob


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REGENERATE = "regenerate"


class RejectReason(StrEnum):
    PRODUCT_CHANGED = "PRODUCT_CHANGED"
    WRONG_COLOR = "WRONG_COLOR"
    WRONG_TEXTURE = "WRONG_TEXTURE"
    WRONG_SHAPE = "WRONG_SHAPE"
    UNREALISTIC_USAGE = "UNREALISTIC_USAGE"
    AI_ARTIFACT = "AI_ARTIFACT"
    TEXT_ERROR = "TEXT_ERROR"
    SIZE_ERROR = "SIZE_ERROR"
    PACKAGING_ERROR = "PACKAGING_ERROR"
    OTHER = "OTHER"


class Review(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reviews"

    asset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset_versions.id", ondelete="RESTRICT"), index=True
    )
    generation_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="RESTRICT"), index=True
    )
    decision: Mapped[ReviewDecision] = mapped_column(Enum(ReviewDecision), index=True)
    reason: Mapped[RejectReason | None] = mapped_column(Enum(RejectReason), nullable=True)
    reviewer: Mapped[str] = mapped_column(String(120))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    job: Mapped["GenerationJob"] = relationship(back_populates="reviews")
