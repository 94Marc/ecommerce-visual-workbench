import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.templates.models import TemplateStatus, TemplateType
from app.templates.schema_types import validate_template_schema


class TemplateVersionInput(BaseModel):
    canvas_width: int = Field(ge=64, le=8192)
    canvas_height: int = Field(ge=64, le=8192)
    background: dict[str, Any] = Field(default_factory=lambda: {"color": "#ffffff"})
    schema_json: dict[str, Any]

    @field_validator("schema_json")
    @classmethod
    def valid_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_template_schema(value)


class TemplateCreate(TemplateVersionInput):
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    template_type: TemplateType
    status: TemplateStatus = TemplateStatus.DRAFT
    preview_asset_id: uuid.UUID | None = None


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    status: TemplateStatus | None = None
    preview_asset_id: uuid.UUID | None = None


class TemplateCopy(BaseModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    name: str | None = Field(default=None, min_length=1, max_length=160)


class TemplateVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_id: uuid.UUID
    version: int
    canvas_width: int
    canvas_height: int
    background: dict[str, Any]
    schema_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    template_type: TemplateType
    status: TemplateStatus
    preview_asset_id: uuid.UUID | None
    versions: list[TemplateVersionRead]
    latest_version: TemplateVersionRead | None
    created_at: datetime
    updated_at: datetime


class TemplateRenderCreate(BaseModel):
    template_version_id: uuid.UUID
    product_id: uuid.UUID
    sku_id: uuid.UUID | None = None
    asset_bindings: dict[str, uuid.UUID] = Field(default_factory=dict)
    asset_slot_id: uuid.UUID | None = None
    output_format: Literal["PNG", "JPEG"] = "PNG"
    quality: int = Field(default=92, ge=1, le=100)
    subject_fill_ratio: float | None = Field(default=None, ge=0.70, le=0.85)
    edge_cleanup: bool = False
    tone_correction: bool = False


class TemplateRenderRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_id: uuid.UUID
    template_version_id: uuid.UUID
    generation_job_id: uuid.UUID
    output_asset_version_id: uuid.UUID
    product_id: uuid.UUID
    sku_id: uuid.UUID | None
    source_asset_version_ids: list[str]
    product_data_snapshot: dict[str, Any]
    rendered_at: datetime


class TemplateRenderRead(BaseModel):
    job_id: uuid.UUID
    output_asset_version_id: uuid.UUID
    record: TemplateRenderRecordRead
