import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.models import AttemptStatus, JobStatus, ValidationStatus
from app.rules.models import ImageSlot, PlatformCode


class GenerationJobCreate(BaseModel):
    source_version_id: uuid.UUID
    platform: PlatformCode
    market: str = Field(min_length=1, max_length=32)
    category: str = Field(min_length=1, max_length=120)
    image_slot: ImageSlot
    visual_plan_id: uuid.UUID | None = None
    asset_slot_id: uuid.UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class VisualPlanGenerationCreate(BaseModel):
    plan_id: uuid.UUID
    source_version_id: uuid.UUID | None = None
    slot_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)


class RegenerationCreate(BaseModel):
    feedback: str | None = Field(default=None, max_length=2000)


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
    attempt_count: int
    max_attempts: int
    timeout_seconds: int
    retryable: bool
    failure_code: str | None
    error_message: str | None
    validation_status: ValidationStatus
    validation_result: dict[str, Any]
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
