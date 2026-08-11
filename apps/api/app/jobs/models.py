import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.rules.models import ImageSlot, PlatformCode


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


class AttemptStatus(StrEnum):
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
        ForeignKey("rule_versions.id", ondelete="RESTRICT")
    )
    visual_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_visual_plans.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    asset_slot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_slots.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    platform: Mapped[PlatformCode] = mapped_column(Enum(PlatformCode), index=True)
    market: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(120))
    image_slot: Mapped[ImageSlot] = mapped_column(Enum(ImageSlot))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING, index=True
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    provider_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt: Mapped[str] = mapped_column(Text, default="")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        Enum(ValidationStatus), default=ValidationStatus.PENDING, index=True
    )
    validation_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GenerationAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "generation_attempts"
    __table_args__ = (UniqueConstraint("generation_job_id", "attempt_number"),)

    generation_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="CASCADE"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[AttemptStatus] = mapped_column(Enum(AttemptStatus), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
