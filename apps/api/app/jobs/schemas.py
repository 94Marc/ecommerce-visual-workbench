import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.models import AttemptStatus, GenerationMode, JobStatus, ValidationStatus
from app.reviews.models import RejectReason
from app.rules.models import ImageSlot, PlatformCode


class GenerationJobCreate(BaseModel):
    source_version_id: uuid.UUID
    reference_asset_version_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    platform: PlatformCode
    market: str = Field(min_length=1, max_length=32)
    category: str = Field(min_length=1, max_length=120)
    image_slot: ImageSlot
    generation_mode: GenerationMode | None = None
    visual_plan_id: uuid.UUID | None = None
    asset_slot_id: uuid.UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class VisualPlanGenerationCreate(BaseModel):
    plan_id: uuid.UUID
    source_version_id: uuid.UUID | None = None
    reference_asset_version_ids: list[uuid.UUID] | None = Field(default=None, max_length=10)
    slot_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    generation_mode: GenerationMode | None = None


class RegenerationCreate(BaseModel):
    feedback: str | None = Field(default=None, max_length=2000)
    reject_reason: RejectReason | None = None


class GenerationQualityCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    generation_job_id: uuid.UUID
    output_version_id: uuid.UUID
    product_similarity: dict[str, Any]
    resolution: dict[str, Any]
    aspect_ratio: dict[str, Any]
    file_size: dict[str, Any]
    format: dict[str, Any]
    text_risk: dict[str, Any]
    watermark_risk: dict[str, Any]
    review_required: bool
    created_at: datetime


class GenerationJobRead(GenerationJobCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resolved_rule_id: uuid.UUID
    parent_job_id: uuid.UUID | None
    output_version_id: uuid.UUID | None
    status: JobStatus
    provider: str
    provider_model: str | None
    provider_request_id: str | None
    prompt: str
    revised_prompt: str | None
    attempt_count: int
    max_attempts: int
    timeout_seconds: int
    retry_count: int
    duration_ms: int | None
    retryable: bool
    failure_code: str | None
    error_message: str | None
    validation_status: ValidationStatus
    validation_result: dict[str, Any]
    quality_check: GenerationQualityCheckRead | None
    review_result: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class GenerationAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    generation_job_id: uuid.UUID
    attempt_number: int
    status: AttemptStatus
    provider: str
    provider_model: str | None
    provider_request_id: str | None
    failure_code: str | None
    retryable: bool
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
