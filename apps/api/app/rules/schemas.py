import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.rules.models import ImageSlot, PlatformCode


class PlatformCreate(BaseModel):
    code: PlatformCode
    name: str = Field(min_length=1, max_length=80)
    enabled: bool = True


class PlatformRead(PlatformCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PlatformMarketCreate(BaseModel):
    platform_id: uuid.UUID
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=80)
    enabled: bool = True


class PlatformMarketRead(PlatformMarketCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PlatformCategoryCreate(BaseModel):
    market_id: uuid.UUID
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=160)
    enabled: bool = True


class PlatformCategoryRead(PlatformCategoryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class RuleVersionCreate(BaseModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    effective_date: date
    min_width: int | None = Field(default=None, gt=0)
    min_height: int | None = Field(default=None, gt=0)
    ratio: str | None = Field(default=None, pattern=r"^\d+(?:\.\d+)?:\d+(?:\.\d+)?$")
    max_size: int | None = Field(default=None, gt=0)
    text_allowed: bool = True
    watermark_allowed: bool = False
    extra_constraints: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class PlatformRuleCreate(BaseModel):
    platform: PlatformCode
    market: str = Field(min_length=1, max_length=32)
    category: str = Field(min_length=1, max_length=120)
    image_slot: ImageSlot
    image_type: ImageSlot | None = None
    version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    rule_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    effective_date: date
    min_width: int | None = Field(default=None, gt=0)
    min_height: int | None = Field(default=None, gt=0)
    ratio: str | None = Field(default=None, pattern=r"^\d+(?:\.\d+)?:\d+(?:\.\d+)?$")
    max_size: int | None = Field(default=None, gt=0)
    text_allowed: bool = True
    watermark_allowed: bool = False
    extra_constraints: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @model_validator(mode="after")
    def normalize_compatibility_fields(self):
        self.version = self.version or self.rule_version
        if not self.version:
            raise ValueError("version is required")
        self.rule_version = self.version
        self.image_type = self.image_type or self.image_slot
        self.min_width = self.min_width or self.constraints.get("min_width")
        self.min_height = self.min_height or self.constraints.get("min_height")
        ratios = self.constraints.get("aspect_ratios") or []
        self.ratio = self.ratio or (ratios[0] if ratios else None)
        if self.max_size is None and self.constraints.get("max_file_size_mb") is not None:
            self.max_size = int(self.constraints["max_file_size_mb"] * 1048576)
        known = {"min_width", "min_height", "aspect_ratios", "max_file_size_mb"}
        self.extra_constraints = {
            **{key: value for key, value in self.constraints.items() if key not in known},
            **self.extra_constraints,
        }
        return self


class PlatformRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    platform_rule_id: uuid.UUID
    platform: PlatformCode
    market: str
    category: str
    image_slot: ImageSlot
    image_type: ImageSlot
    version: str
    rule_version: str
    effective_date: date
    min_width: int | None
    min_height: int | None
    ratio: str | None
    max_size: int | None
    text_allowed: bool
    watermark_allowed: bool
    extra_constraints: dict[str, Any]
    constraints: dict[str, Any]
    enabled: bool
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
    has_text: bool = False
    has_watermark: bool = False


class RuleValidationResult(BaseModel):
    valid: bool
    violations: list[str]
