import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.rules.models import ImageSlot


class ProductVisualPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_visual_plans"
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    platform_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platforms.id", ondelete="RESTRICT"), index=True
    )
    rule_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rule_versions.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    market: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(120))
    requested_outputs: Mapped[dict[str, int]] = mapped_column(JSON)
    slots: Mapped[list["AssetSlot"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="AssetSlot.position",
        lazy="selectin",
    )


class AssetSlot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asset_slots"
    __table_args__ = (
        UniqueConstraint("product_visual_plan_id", "code"),
        UniqueConstraint("product_visual_plan_id", "position"),
    )
    product_visual_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_visual_plans.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(80), index=True)
    image_type: Mapped[ImageSlot] = mapped_column(String(32), index=True)
    position: Mapped[int] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    plan: Mapped[ProductVisualPlan] = relationship(back_populates="slots")
