from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.rules.models import ImageSlot, PlatformCode, PlatformRule
from app.rules.schemas import ImageProbe, PlatformRuleCreate, RuleValidationResult


class RuleNotFoundError(LookupError):
    pass


class DuplicateRuleError(ValueError):
    pass


class RuleService:
    def __init__(self, session: Session):
        self.session = session

    def create_rule(self, data: PlatformRuleCreate) -> PlatformRule:
        rule = PlatformRule(**data.model_dump())
        self.session.add(rule)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateRuleError("rule version already exists for this scope") from exc
        self.session.refresh(rule)
        return rule

    def list_rules(self, platform: PlatformCode | None = None) -> list[PlatformRule]:
        statement = select(PlatformRule)
        if platform:
            statement = statement.where(PlatformRule.platform == platform)
        statement = statement.order_by(
            PlatformRule.platform,
            PlatformRule.image_slot,
            PlatformRule.effective_date.desc(),
        )
        return list(self.session.scalars(statement))

    def resolve(
        self,
        platform: PlatformCode,
        market: str,
        category: str,
        image_slot: ImageSlot,
        as_of: date | None = None,
    ) -> PlatformRule:
        target_date = as_of or date.today()
        statement = (
            select(PlatformRule)
            .where(
                PlatformRule.platform == platform,
                PlatformRule.market.in_([market, "*"]),
                PlatformRule.category.in_([category, "*"]),
                PlatformRule.image_slot == image_slot,
                PlatformRule.effective_date <= target_date,
                PlatformRule.enabled.is_(True),
            )
            .order_by(
                (PlatformRule.market == market).desc(),
                (PlatformRule.category == category).desc(),
                PlatformRule.effective_date.desc(),
                PlatformRule.rule_version.desc(),
            )
            .limit(1)
        )
        rule = self.session.scalar(statement)
        if rule is None:
            raise RuleNotFoundError(
                f"no effective rule for {platform}/{market}/{category}/{image_slot}"
            )
        return rule

    def validate_image(self, rule: PlatformRule, image: ImageProbe) -> RuleValidationResult:
        constraints = rule.constraints
        violations: list[str] = []
        if image.width < constraints.get("min_width", 0):
            violations.append(f"width must be at least {constraints['min_width']}px")
        if image.height < constraints.get("min_height", 0):
            violations.append(f"height must be at least {constraints['min_height']}px")
        max_size = constraints.get("max_file_size_mb")
        if max_size is not None and image.byte_size > max_size * 1024 * 1024:
            violations.append(f"file must be no larger than {max_size}MB")
        formats = constraints.get("formats")
        if formats and image.mime_type not in formats:
            violations.append(f"format must be one of {', '.join(formats)}")
        ratios = constraints.get("aspect_ratios")
        if ratios:
            actual = image.width / image.height
            if not any(abs(actual - self._parse_ratio(value)) <= 0.02 for value in ratios):
                violations.append(f"aspect ratio must be one of {', '.join(ratios)}")
        return RuleValidationResult(valid=not violations, violations=violations)

    @staticmethod
    def _parse_ratio(value: str) -> float:
        width, height = value.split(":", 1)
        return float(width) / float(height)

