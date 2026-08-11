import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class TemplateType(StrEnum):
    MAIN = "MAIN"
    DETAIL = "DETAIL"
    DIMENSION = "DIMENSION"
    SELLING_POINT = "SELLING_POINT"
    PARAMETER = "PARAMETER"
    PACKAGE = "PACKAGE"
    COMPARE = "COMPARE"


class TemplateStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class Template(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "templates"

    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    template_type: Mapped[TemplateType] = mapped_column(Enum(TemplateType), index=True)
    status: Mapped[TemplateStatus] = mapped_column(
        Enum(TemplateStatus), default=TemplateStatus.DRAFT, index=True
    )
    preview_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    versions: Mapped[list["TemplateVersion"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateVersion.version",
        lazy="selectin",
    )

    @property
    def latest_version(self) -> "TemplateVersion | None":
        return self.versions[-1] if self.versions else None


class TemplateVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    canvas_width: Mapped[int] = mapped_column(Integer)
    canvas_height: Mapped[int] = mapped_column(Integer)
    background: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    template: Mapped[Template] = relationship(back_populates="versions")


class TemplateRenderRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "template_render_records"

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("templates.id", ondelete="RESTRICT"), index=True
    )
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("template_versions.id", ondelete="RESTRICT"), index=True
    )
    generation_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="RESTRICT"), unique=True, index=True
    )
    output_asset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset_versions.id", ondelete="RESTRICT"), unique=True, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    sku_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("skus.id", ondelete="SET NULL"), nullable=True
    )
    source_asset_version_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    product_data_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rendered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
