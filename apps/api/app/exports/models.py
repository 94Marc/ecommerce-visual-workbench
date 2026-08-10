import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.rules.models import PlatformCode


class ExportStatus(StrEnum):
    READY = "ready"
    FAILED = "failed"


class ExportBundle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "export_bundles"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    platform: Mapped[PlatformCode] = mapped_column(Enum(PlatformCode), index=True)
    market: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(120))
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[ExportStatus] = mapped_column(Enum(ExportStatus), default=ExportStatus.READY)

