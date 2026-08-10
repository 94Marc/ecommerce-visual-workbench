import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.rules.models import ImageSlot, PlatformCode


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "generation_jobs"

    source_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset_versions.id", ondelete="RESTRICT"), index=True
    )
    output_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_versions.id", ondelete="SET NULL"), nullable=True
    )
    resolved_rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_rules.id", ondelete="RESTRICT")
    )
    platform: Mapped[PlatformCode] = mapped_column(Enum(PlatformCode), index=True)
    market: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(120))
    image_slot: Mapped[ImageSlot] = mapped_column(Enum(ImageSlot))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING, index=True
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
