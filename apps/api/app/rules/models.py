from datetime import date
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Date, Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin


class PlatformCode(StrEnum):
    TEMU = "temu"
    AMAZON = "amazon"
    TIKTOK_SHOP = "tiktok_shop"
    SHOPEE = "shopee"
    ALIEXPRESS = "aliexpress"


class ImageSlot(StrEnum):
    MAIN = "MAIN"
    DETAIL = "DETAIL"
    DIMENSION = "DIMENSION"
    SCENE = "SCENE"
    USAGE = "USAGE"
    PACKAGE = "PACKAGE"
    CLOSEUP = "CLOSEUP"
    COMPARE = "COMPARE"


class PlatformRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_rules"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "market",
            "category",
            "image_slot",
            "rule_version",
            name="uq_platform_rule_version",
        ),
    )

    platform: Mapped[PlatformCode] = mapped_column(Enum(PlatformCode), index=True)
    market: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(120), index=True)
    image_slot: Mapped[ImageSlot] = mapped_column(Enum(ImageSlot), index=True)
    rule_version: Mapped[str] = mapped_column(String(32))
    effective_date: Mapped[date] = mapped_column(Date, index=True)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
