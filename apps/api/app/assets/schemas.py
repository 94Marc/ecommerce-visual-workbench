import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.assets.models import AssetStatus, AssetType


class AssetVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    version_number: int
    object_key: str
    original_filename: str
    mime_type: str
    byte_size: int
    width: int | None
    height: int | None
    checksum_sha256: str
    source_version_id: uuid.UUID | None
    status: AssetStatus
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    sku_id: uuid.UUID | None
    asset_slot_id: uuid.UUID | None
    asset_type: AssetType
    label: str | None
    is_archived: bool
    archived_at: datetime | None
    versions: list[AssetVersionRead]
    created_at: datetime


class AssetUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    asset_slot_id: uuid.UUID | None = None


class AssetVersionUpdate(BaseModel):
    status: AssetStatus
