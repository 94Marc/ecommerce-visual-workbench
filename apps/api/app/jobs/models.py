import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.rules.models import ImageSlot, PlatformCode

if TYPE_CHECKING:
    from app.reviews.models import Review


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


class GenerationMode(StrEnum):
    STRICT = "STRICT"
    BALANCED = "BALANCED"
    CREATIVE = "CREATIVE"


class TaskType(StrEnum):
    REMOVE_BACKGROUND = "REMOVE_BACKGROUND"
    UPSCALE = "UPSCALE"
    GENERATE_SCENE = "GENERATE_SCENE"
    GENERATE_USAGE = "GENERATE_USAGE"
    GENERATE_BACKGROUND = "GENERATE_BACKGROUND"
    GENERATE_DETAIL = "GENERATE_DETAIL"
    GENERATE_MAIN = "GENERATE_MAIN"
    RENDER_MAIN_TEMPLATE = "RENDER_MAIN_TEMPLATE"
    RENDER_DIMENSION_TEMPLATE = "RENDER_DIMENSION_TEMPLATE"
    RENDER_DETAIL_TEMPLATE = "RENDER_DETAIL_TEMPLATE"
    RENDER_SELLING_POINT_TEMPLATE = "RENDER_SELLING_POINT_TEMPLATE"
    RENDER_PARAMETER_TEMPLATE = "RENDER_PARAMETER_TEMPLATE"
    RENDER_PACKAGE_TEMPLATE = "RENDER_PACKAGE_TEMPLATE"
    RENDER_COMPARE_TEMPLATE = "RENDER_COMPARE_TEMPLATE"

    @property
    def is_generation(self) -> bool:
        return self.value.startswith("GENERATE_")

    @property
    def is_template(self) -> bool:
        return self.value.startswith("RENDER_")


class ProviderType(StrEnum):
    AI = "AI"
    IMAGE_PROCESSING = "IMAGE_PROCESSING"
    TEMPLATE = "TEMPLATE"


class UpscaleMode(StrEnum):
    CONSERVATIVE = "CONSERVATIVE"
    TWO_X = "2X"
    FOUR_X = "4X"


class WorkflowDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflow_definitions"
    __table_args__ = (UniqueConstraint("name", "version"),)

    name: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(32))
    task_type: Mapped[TaskType] = mapped_column(Enum(TaskType), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    workflow_file: Mapped[str] = mapped_column(String(500))
    default_parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class GenerationJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "generation_jobs"

    source_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset_versions.id", ondelete="RESTRICT"), index=True
    )
    output_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_versions.id", ondelete="SET NULL"), nullable=True
    )
    resolved_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rule_versions.id", ondelete="RESTRICT"), nullable=True
    )
    workflow_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="RESTRICT"), nullable=True, index=True
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
    platform: Mapped[PlatformCode | None] = mapped_column(
        Enum(PlatformCode), nullable=True, index=True
    )
    market: Mapped[str | None] = mapped_column(String(32), nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    image_slot: Mapped[ImageSlot | None] = mapped_column(Enum(ImageSlot), nullable=True)
    task_type: Mapped[TaskType] = mapped_column(
        Enum(TaskType), default=TaskType.GENERATE_MAIN, index=True
    )
    generation_mode: Mapped[GenerationMode] = mapped_column(
        Enum(GenerationMode), default=GenerationMode.STRICT, index=True
    )
    reference_asset_version_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING, index=True
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    provider_type: Mapped[ProviderType] = mapped_column(
        Enum(ProviderType), default=ProviderType.AI, index=True
    )
    provider_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt: Mapped[str] = mapped_column(Text, default="")
    revised_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
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
    output_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_check: Mapped["GenerationQualityCheck | None"] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan", lazy="joined"
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="job", order_by="Review.created_at", lazy="selectin"
    )

    @property
    def retry_count(self) -> int:
        return max(0, self.attempt_count - 1)

    @property
    def review_result(self) -> dict[str, Any] | None:
        active = [review for review in self.reviews if not review.is_deleted]
        if not active:
            return None
        review = active[-1]
        return {
            "decision": review.decision.value,
            "reason": review.reason.value if review.reason else None,
            "comment": review.comment,
            "reviewer": review.reviewer,
            "created_at": review.created_at.isoformat(),
        }


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
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class GenerationQualityCheck(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "generation_quality_checks"

    generation_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="CASCADE"), unique=True, index=True
    )
    output_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset_versions.id", ondelete="RESTRICT"), index=True
    )
    product_similarity: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resolution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    aspect_ratio: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    file_size: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    format: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    text_risk: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    watermark_risk: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    job: Mapped[GenerationJob] = relationship(back_populates="quality_check")
