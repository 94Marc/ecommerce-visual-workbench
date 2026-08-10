import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.rules.models import (
    ImageSlot,
    Platform,
    PlatformCategory,
    PlatformCode,
    PlatformMarket,
    PlatformRule,
    RuleVersion,
)
from app.rules.schemas import (
    ImageProbe,
    PlatformCategoryCreate,
    PlatformCreate,
    PlatformMarketCreate,
    PlatformRuleCreate,
    RuleValidationResult,
    RuleVersionCreate,
)


class RuleNotFoundError(LookupError):
    pass


class DuplicateRuleError(ValueError):
    pass


class RuleService:
    PLATFORM_NAMES = {
        PlatformCode.TEMU: "Temu",
        PlatformCode.AMAZON: "Amazon",
        PlatformCode.TIKTOK_SHOP: "TikTok Shop",
        PlatformCode.SHOPEE: "Shopee",
        PlatformCode.ALIEXPRESS: "AliExpress",
    }

    def __init__(self, session: Session):
        self.session = session

    def create_platform(self, data: PlatformCreate) -> Platform:
        return self._commit_unique(
            Platform(**data.model_dump(mode="json")), "platform already exists"
        )

    def list_platforms(self) -> list[Platform]:
        return list(self.session.scalars(select(Platform).order_by(Platform.name)))

    def create_market(self, data: PlatformMarketCreate) -> PlatformMarket:
        if self.session.get(Platform, data.platform_id) is None:
            raise RuleNotFoundError(f"platform {data.platform_id} not found")
        return self._commit_unique(
            PlatformMarket(**data.model_dump()), "market already exists for this platform"
        )

    def list_markets(self, platform_id: uuid.UUID | None = None) -> list[PlatformMarket]:
        statement = select(PlatformMarket)
        if platform_id:
            statement = statement.where(PlatformMarket.platform_id == platform_id)
        return list(self.session.scalars(statement.order_by(PlatformMarket.code)))

    def create_category(self, data: PlatformCategoryCreate) -> PlatformCategory:
        if self.session.get(PlatformMarket, data.market_id) is None:
            raise RuleNotFoundError(f"market {data.market_id} not found")
        return self._commit_unique(
            PlatformCategory(**data.model_dump()), "category already exists for this market"
        )

    def list_categories(self, market_id: uuid.UUID | None = None) -> list[PlatformCategory]:
        statement = select(PlatformCategory)
        if market_id:
            statement = statement.where(PlatformCategory.market_id == market_id)
        return list(self.session.scalars(statement.order_by(PlatformCategory.code)))

    def create_rule(self, data: PlatformRuleCreate) -> RuleVersion:
        platform = self._get_or_create_platform(data.platform)
        market = self._get_or_create_market(platform, data.market)
        category = self._get_or_create_category(market, data.category)
        rule = self.session.scalar(
            select(PlatformRule).where(
                PlatformRule.category_id == category.id,
                PlatformRule.image_slot == data.image_slot,
                PlatformRule.image_type == data.image_type,
            )
        )
        if rule is None:
            rule = PlatformRule(
                category_id=category.id, image_slot=data.image_slot, image_type=data.image_type
            )
            self.session.add(rule)
            self.session.flush()
        version = RuleVersion(
            platform_rule_id=rule.id,
            version=data.version,
            effective_date=data.effective_date,
            min_width=data.min_width,
            min_height=data.min_height,
            ratio=data.ratio,
            max_size=data.max_size,
            text_allowed=data.text_allowed,
            watermark_allowed=data.watermark_allowed,
            extra_constraints=data.extra_constraints,
            enabled=data.enabled,
        )
        return self._commit_unique(version, "rule version already exists for this scope")

    def add_version(self, rule_id: uuid.UUID, data: RuleVersionCreate) -> RuleVersion:
        if self.session.get(PlatformRule, rule_id) is None:
            raise RuleNotFoundError(f"platform rule {rule_id} not found")
        return self._commit_unique(
            RuleVersion(platform_rule_id=rule_id, **data.model_dump()),
            "rule version already exists for this scope",
        )

    def list_rules(self, platform: PlatformCode | None = None) -> list[RuleVersion]:
        statement = (
            select(RuleVersion)
            .join(RuleVersion.rule)
            .join(PlatformRule.category)
            .join(PlatformCategory.market)
            .join(PlatformMarket.platform)
        )
        if platform:
            statement = statement.where(Platform.code == platform.value)
        return list(
            self.session.scalars(
                statement.order_by(
                    Platform.code, PlatformRule.image_slot, RuleVersion.effective_date.desc()
                )
            )
        )

    def resolve(
        self,
        platform: PlatformCode,
        market: str,
        category: str,
        image_slot: ImageSlot,
        as_of: date | None = None,
    ) -> RuleVersion:
        target_date = as_of or date.today()
        statement = (
            select(RuleVersion)
            .join(RuleVersion.rule)
            .join(PlatformRule.category)
            .join(PlatformCategory.market)
            .join(PlatformMarket.platform)
            .where(
                Platform.code == platform.value,
                PlatformMarket.code.in_([market, "*"]),
                PlatformCategory.code.in_([category, "*"]),
                PlatformRule.image_slot == image_slot,
                RuleVersion.effective_date <= target_date,
                RuleVersion.enabled.is_(True),
                Platform.enabled.is_(True),
                PlatformMarket.enabled.is_(True),
                PlatformCategory.enabled.is_(True),
            )
        )
        candidates = list(self.session.scalars(statement))
        if not candidates:
            raise RuleNotFoundError(
                f"no effective rule for {platform}/{market}/{category}/{image_slot}"
            )
        return max(
            candidates,
            key=lambda item: (
                item.market == market,
                item.category == category,
                item.effective_date,
                self._parse_version(item.version),
            ),
        )

    def validate_image(self, rule: RuleVersion, image: ImageProbe) -> RuleValidationResult:
        violations: list[str] = []
        if rule.min_width is not None and image.width < rule.min_width:
            violations.append(f"width must be at least {rule.min_width}px")
        if rule.min_height is not None and image.height < rule.min_height:
            violations.append(f"height must be at least {rule.min_height}px")
        if rule.max_size is not None and image.byte_size > rule.max_size:
            violations.append(f"file must be no larger than {rule.max_size} bytes")
        formats = rule.extra_constraints.get("formats")
        if formats and image.mime_type not in formats:
            violations.append(f"format must be one of {', '.join(formats)}")
        if rule.ratio and abs(image.width / image.height - self._parse_ratio(rule.ratio)) > 0.02:
            violations.append(f"aspect ratio must be {rule.ratio}")
        if image.has_text and not rule.text_allowed:
            violations.append("text is not allowed")
        if image.has_watermark and not rule.watermark_allowed:
            violations.append("watermark is not allowed")
        return RuleValidationResult(valid=not violations, violations=violations)

    def _get_or_create_platform(self, code: PlatformCode) -> Platform:
        item = self.session.scalar(select(Platform).where(Platform.code == code.value))
        if item is None:
            item = Platform(code=code.value, name=self.PLATFORM_NAMES[code])
            self.session.add(item)
            self.session.flush()
        return item

    def _get_or_create_market(self, platform: Platform, code: str) -> PlatformMarket:
        item = self.session.scalar(
            select(PlatformMarket).where(
                PlatformMarket.platform_id == platform.id, PlatformMarket.code == code
            )
        )
        if item is None:
            item = PlatformMarket(platform_id=platform.id, code=code, name=code)
            self.session.add(item)
            self.session.flush()
        return item

    def _get_or_create_category(self, market: PlatformMarket, code: str) -> PlatformCategory:
        item = self.session.scalar(
            select(PlatformCategory).where(
                PlatformCategory.market_id == market.id, PlatformCategory.code == code
            )
        )
        if item is None:
            item = PlatformCategory(market_id=market.id, code=code, name=code)
            self.session.add(item)
            self.session.flush()
        return item

    def _commit_unique(self, model, message: str):
        self.session.add(model)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateRuleError(message) from exc
        self.session.refresh(model)
        return model

    @staticmethod
    def _parse_ratio(value: str) -> float:
        width, height = value.split(":", 1)
        return float(width) / float(height)

    @staticmethod
    def _parse_version(value: str) -> tuple[int, int, int]:
        major, minor, patch = (int(part) for part in value.split("."))
        return major, minor, patch
