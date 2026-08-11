import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.models import (
    AttemptStatus,
    GenerationMode,
    JobStatus,
    ProviderType,
    TaskType,
    UpscaleMode,
    ValidationStatus,
)
from app.reviews.models import RejectReason
from app.rules.models import ImageSlot, PlatformCode


class GenerationJobCreate(BaseModel):
    source_version_id: uuid.UUID
    reference_asset_version_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    platform: PlatformCode | None = None
    market: str | None = Field(default=None, min_length=1, max_length=32)
    category: str | None = Field(default=None, min_length=1, max_length=120)
    image_slot: ImageSlot | None = None
    task_type: TaskType | None = None
    generation_mode: GenerationMode | None = None
    visual_plan_id: uuid.UUID | None = None
    asset_slot_id: uuid.UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ImageProcessingTaskCreate(BaseModel):
    source_version_id: uuid.UUID
    task_type: TaskType
    reference_asset_version_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    workflow_id: uuid.UUID | None = None
    prompt: str | None = Field(default=None, max_length=8000)
    negative_prompt: str | None = Field(default=None, max_length=4000)
    generation_mode: GenerationMode | None = None
    seed: int | None = Field(default=None, ge=0, le=9223372036854775807)
    width: int | None = Field(default=None, ge=64, le=8192)
    height: int | None = Field(default=None, ge=64, le=8192)
    upscale_mode: UpscaleMode = UpscaleMode.CONSERVATIVE
    tile: int | None = Field(default=None, ge=0, le=2048)
    platform: PlatformCode | None = None
    market: str | None = Field(default=None, min_length=1, max_length=32)
    category: str | None = Field(default=None, min_length=1, max_length=120)
    image_slot: ImageSlot | None = None


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
    resolved_rule_id: uuid.UUID | None
    workflow_definition_id: uuid.UUID | None
    parent_job_id: uuid.UUID | None
    output_version_id: uuid.UUID | None
    status: JobStatus
    provider: str
    provider_type: ProviderType
    provider_model: str | None
    provider_request_id: str | None
    prompt: str
    revised_prompt: str | None
    negative_prompt: str | None
    seed: int | None
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
    output_metadata: dict[str, Any]
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


class WorkflowDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: str
    task_type: TaskType
    provider: str
    workflow_file: str
    default_parameters: dict[str, Any]
    active: bool
    created_at: datetime
    updated_at: datetime
