import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.models import JobStatus
from app.rules.models import ImageSlot, PlatformCode


class GenerationJobCreate(BaseModel):
    source_version_id: uuid.UUID
    platform: PlatformCode
    market: str = Field(min_length=1, max_length=32)
    category: str = Field(min_length=1, max_length=120)
    image_slot: ImageSlot
    parameters: dict[str, Any] = Field(default_factory=dict)


class GenerationJobRead(GenerationJobCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resolved_rule_id: uuid.UUID
    output_version_id: uuid.UUID | None
    status: JobStatus
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
