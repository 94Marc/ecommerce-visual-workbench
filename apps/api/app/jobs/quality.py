from dataclasses import dataclass
from typing import Any, Protocol

from app.jobs.providers import ImageGenerationResult, ReferenceImage
from app.rules.models import RuleVersion


@dataclass(frozen=True)
class AnalyzerResult:
    status: str
    score: float | None = None
    risk: str | None = None
    details: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "status": self.status,
                "score": self.score,
                "risk": self.risk,
                "details": self.details,
            }.items()
            if value is not None
        }


class ProductSimilarityAnalyzer(Protocol):
    name: str

    def analyze(
        self, output: ImageGenerationResult, references: tuple[ReferenceImage, ...]
    ) -> AnalyzerResult: ...


class TextRiskAnalyzer(Protocol):
    name: str

    def analyze(self, output: ImageGenerationResult) -> AnalyzerResult: ...


class WatermarkRiskAnalyzer(Protocol):
    name: str

    def analyze(self, output: ImageGenerationResult) -> AnalyzerResult: ...


class UnavailableProductSimilarityAnalyzer:
    name = "unavailable"

    def analyze(
        self, output: ImageGenerationResult, references: tuple[ReferenceImage, ...]
    ) -> AnalyzerResult:
        return AnalyzerResult(
            status="unavailable",
            details="no product similarity analyzer is configured",
        )


class UnavailableTextRiskAnalyzer:
    name = "unavailable"

    def analyze(self, output: ImageGenerationResult) -> AnalyzerResult:
        return AnalyzerResult(status="unavailable", details="no text risk analyzer is configured")


class UnavailableWatermarkRiskAnalyzer:
    name = "unavailable"

    def analyze(self, output: ImageGenerationResult) -> AnalyzerResult:
        return AnalyzerResult(
            status="unavailable", details="no watermark risk analyzer is configured"
        )


@dataclass(frozen=True)
class GenerationQualityResult:
    product_similarity: dict[str, Any]
    resolution: dict[str, Any]
    aspect_ratio: dict[str, Any]
    file_size: dict[str, Any]
    format: dict[str, Any]
    text_risk: dict[str, Any]
    watermark_risk: dict[str, Any]
    review_required: bool

    @property
    def measurable_checks_passed(self) -> bool:
        return all(
            item["status"] == "passed"
            for item in (self.resolution, self.aspect_ratio, self.file_size, self.format)
        )


class GenerationQualityEvaluator:
    def __init__(
        self,
        product_similarity: ProductSimilarityAnalyzer | None = None,
        text_risk: TextRiskAnalyzer | None = None,
        watermark_risk: WatermarkRiskAnalyzer | None = None,
    ) -> None:
        self.product_similarity = product_similarity or UnavailableProductSimilarityAnalyzer()
        self.text_risk = text_risk or UnavailableTextRiskAnalyzer()
        self.watermark_risk = watermark_risk or UnavailableWatermarkRiskAnalyzer()

    def evaluate(
        self,
        rule: RuleVersion,
        output: ImageGenerationResult,
        references: tuple[ReferenceImage, ...],
    ) -> GenerationQualityResult:
        resolution_valid = (rule.min_width is None or output.width >= rule.min_width) and (
            rule.min_height is None or output.height >= rule.min_height
        )
        resolution = self._check(
            resolution_valid,
            actual={"width": output.width, "height": output.height},
            expected={"min_width": rule.min_width, "min_height": rule.min_height},
        )

        actual_ratio = output.width / output.height
        expected_ratio = self._parse_ratio(rule.ratio) if rule.ratio else None
        ratio_valid = expected_ratio is None or abs(actual_ratio - expected_ratio) <= 0.02
        aspect_ratio = self._check(
            ratio_valid,
            actual=round(actual_ratio, 4),
            expected=rule.ratio,
        )

        file_size_valid = rule.max_size is None or len(output.content) <= rule.max_size
        file_size = self._check(
            file_size_valid,
            actual=len(output.content),
            expected={"max_bytes": rule.max_size},
        )

        formats = rule.extra_constraints.get("formats") or []
        format_valid = not formats or output.mime_type in formats
        image_format = self._check(format_valid, actual=output.mime_type, expected=formats or None)

        return GenerationQualityResult(
            product_similarity=self.product_similarity.analyze(output, references).as_dict(),
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            file_size=file_size,
            format=image_format,
            text_risk=self.text_risk.analyze(output).as_dict(),
            watermark_risk=self.watermark_risk.analyze(output).as_dict(),
            review_required=True,
        )

    @staticmethod
    def _check(valid: bool, *, actual: Any, expected: Any) -> dict[str, Any]:
        return {
            "status": "passed" if valid else "failed",
            "actual": actual,
            "expected": expected,
        }

    @staticmethod
    def _parse_ratio(value: str) -> float:
        width, height = value.split(":", 1)
        return float(width) / float(height)
