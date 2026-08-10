import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.rules.models import ImageSlot, PlatformCode


class PlatformRuleCreate(BaseModel):
    platform: PlatformCode
    market: str = Field(min_length=1, max_length=32)
    category: str = Field(min_length=1, max_length=120)
    image_slot: ImageSlot
    rule_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    effective_date: date
    constraints: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class PlatformRuleRead(PlatformRuleCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class RuleResolutionRequest(BaseModel):
    platform: PlatformCode
    market: str
    category: str
    image_slot: ImageSlot
    as_of: date | None = None


class ImageProbe(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    mime_type: str
    byte_size: int = Field(gt=0)


class RuleValidationResult(BaseModel):
    valid: bool
    violations: list[str]

