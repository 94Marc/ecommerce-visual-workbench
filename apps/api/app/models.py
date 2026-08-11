"""Import all ORM models so metadata and migrations discover them."""

from app.assets.models import Asset, AssetVersion
from app.catalog.models import SKU, Product
from app.exports.models import ExportBundle
from app.jobs.models import GenerationAttempt, GenerationJob, GenerationQualityCheck
from app.plans.models import AssetSlot, ProductVisualPlan
from app.reviews.models import Review
from app.rules.models import Platform, PlatformCategory, PlatformMarket, PlatformRule, RuleVersion

__all__ = [
    "Asset",
    "AssetVersion",
    "AssetSlot",
    "ExportBundle",
    "GenerationJob",
    "GenerationAttempt",
    "GenerationQualityCheck",
    "PlatformRule",
    "Platform",
    "PlatformCategory",
    "PlatformMarket",
    "Product",
    "ProductVisualPlan",
    "Review",
    "SKU",
    "RuleVersion",
]
