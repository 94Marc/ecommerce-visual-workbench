import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.exports.models import ExportStatus
from app.rules.models import PlatformCode


class ExportCreate(BaseModel):
    product_id: uuid.UUID
    platform: PlatformCode
    market: str = Field(min_length=1, max_length=32)
    category: str = Field(min_length=1, max_length=120)


class ExportRead(ExportCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    object_key: str
    manifest: dict[str, Any]
    checksum_sha256: str
    status: ExportStatus
    created_at: datetime
