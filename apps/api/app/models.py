"""Import all ORM models so metadata and migrations discover them."""

from app.assets.models import Asset, AssetVersion
from app.catalog.models import SKU, Product
from app.exports.models import ExportBundle
from app.jobs.models import (
    GenerationAttempt,
    GenerationJob,
    GenerationQualityCheck,
    WorkflowDefinition,
)
from app.plans.models import AssetSlot, ProductVisualPlan
from app.reviews.models import Review
from app.rules.models import Platform, PlatformCategory, PlatformMarket, PlatformRule, RuleVersion
from app.templates.models import Template, TemplateRenderRecord, TemplateVersion

__all__ = [
    "Asset",
    "AssetVersion",
    "AssetSlot",
    "ExportBundle",
    "GenerationJob",
    "GenerationAttempt",
    "GenerationQualityCheck",
    "WorkflowDefinition",
    "PlatformRule",
    "Platform",
    "PlatformCategory",
    "PlatformMarket",
    "Product",
    "ProductVisualPlan",
    "Review",
    "SKU",
    "Template",
    "TemplateRenderRecord",
    "TemplateVersion",
    "RuleVersion",
]
