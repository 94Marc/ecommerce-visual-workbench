import uuid
from datetime import date
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class Platform(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platforms"
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    markets: Mapped[list["PlatformMarket"]] = relationship(
        back_populates="platform", cascade="all, delete-orphan", lazy="selectin"
    )


class PlatformMarket(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_markets"
    __table_args__ = (UniqueConstraint("platform_id", "code"),)
    platform_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platforms.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    platform: Mapped[Platform] = relationship(back_populates="markets")
    categories: Mapped[list["PlatformCategory"]] = relationship(
        back_populates="market", cascade="all, delete-orphan", lazy="selectin"
    )


class PlatformCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_categories"
    __table_args__ = (UniqueConstraint("market_id", "code"),)
    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_markets.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    market: Mapped[PlatformMarket] = relationship(back_populates="categories")
    rules: Mapped[list["PlatformRule"]] = relationship(
        back_populates="category", cascade="all, delete-orphan", lazy="selectin"
    )


class PlatformRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_rules"
    __table_args__ = (UniqueConstraint("category_id", "image_slot", "image_type"),)
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_categories.id", ondelete="CASCADE"), index=True
    )
    image_slot: Mapped[ImageSlot] = mapped_column(String(32), index=True)
    image_type: Mapped[ImageSlot] = mapped_column(String(32), index=True)
    category: Mapped[PlatformCategory] = relationship(back_populates="rules")
    versions: Mapped[list["RuleVersion"]] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
        order_by="RuleVersion.effective_date",
        lazy="selectin",
    )


class RuleVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rule_versions"
    __table_args__ = (UniqueConstraint("platform_rule_id", "version"),)
    platform_rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_rules.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(32))
    effective_date: Mapped[date] = mapped_column(Date, index=True)
    min_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ratio: Mapped[str | None] = mapped_column(String(32), nullable=True)
    max_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    watermark_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    rule: Mapped[PlatformRule] = relationship(back_populates="versions", lazy="joined")

    @property
    def platform(self) -> str:
        return self.rule.category.market.platform.code

    @property
    def market(self) -> str:
        return self.rule.category.market.code

    @property
    def category(self) -> str:
        return self.rule.category.code

    @property
    def image_slot(self) -> ImageSlot:
        return self.rule.image_slot

    @property
    def image_type(self) -> ImageSlot:
        return self.rule.image_type

    @property
    def rule_version(self) -> str:
        return self.version

    @property
    def constraints(self) -> dict[str, Any]:
        values = dict(self.extra_constraints)
        if self.min_width is not None:
            values["min_width"] = self.min_width
        if self.min_height is not None:
            values["min_height"] = self.min_height
        if self.ratio:
            values["aspect_ratios"] = [self.ratio]
        if self.max_size is not None:
            values["max_size"] = self.max_size
            values["max_file_size_mb"] = self.max_size / 1048576
        values.update(text_allowed=self.text_allowed, watermark_allowed=self.watermark_allowed)
        return values
