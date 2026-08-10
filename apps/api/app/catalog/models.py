import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(120), index=True)
    material: Mapped[str | None] = mapped_column(String(120), nullable=True)
    color: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    weight_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    selling_points: Mapped[list[str]] = mapped_column(JSON, default=list)

    skus: Mapped[list["SKU"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )


class SKU(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "skus"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    product: Mapped[Product] = relationship(back_populates="skus")
