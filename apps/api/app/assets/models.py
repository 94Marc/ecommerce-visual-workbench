import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class AssetType(StrEnum):
    ORIGINAL = "ORIGINAL"
    CUTOUT = "CUTOUT"
    MAIN = "MAIN"
    DETAIL = "DETAIL"
    DIMENSION = "DIMENSION"
    SCENE = "SCENE"
    USAGE = "USAGE"
    PACKAGE = "PACKAGE"
    CLOSEUP = "CLOSEUP"
    COMPARE = "COMPARE"


class AssetStatus(StrEnum):
    DRAFT = "DRAFT"
    PROCESSING = "PROCESSING"
    REVIEW = "REVIEW"
    APPROVED_FOR_SMOKE_TEST = "APPROVED_FOR_SMOKE_TEST"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assets"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    sku_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("skus.id", ondelete="SET NULL"), nullable=True, index=True
    )
    asset_slot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_slots.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    asset_type: Mapped[AssetType] = mapped_column(Enum(AssetType), index=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list["AssetVersion"]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
        order_by="AssetVersion.version_number",
        lazy="selectin",
    )


class AssetVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "asset_versions"
    __table_args__ = (UniqueConstraint("asset_id", "version_number"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_versions.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus), default=AssetStatus.DRAFT, index=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    asset: Mapped[Asset] = relationship(back_populates="versions")
