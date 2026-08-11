import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets.models import Asset, AssetStatus, AssetType, AssetVersion
from app.catalog.models import SKU, Product

SUPPORTED_UNITS = {"mm", "cm", "m", "inch"}
UNIT_TO_MM = {
    "mm": Decimal("1"),
    "cm": Decimal("10"),
    "m": Decimal("1000"),
    "inch": Decimal("25.4"),
}
VARIABLE_PATTERN = re.compile(r"\{\{([a-zA-Z0-9_.]+)\}\}")


class TemplateBindingError(ValueError):
    pass


def format_dimension(value: Any, source_unit: str, target_unit: str | None = None) -> str:
    if source_unit not in SUPPORTED_UNITS:
        raise TemplateBindingError(f"unsupported dimension unit {source_unit}")
    destination = target_unit or source_unit
    if destination not in SUPPORTED_UNITS:
        raise TemplateBindingError(f"unsupported dimension unit {destination}")
    converted = Decimal(str(value)) * UNIT_TO_MM[source_unit] / UNIT_TO_MM[destination]
    normalized = converted.quantize(Decimal("0.01")).normalize()
    formatted = format(normalized, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return f"{formatted or '0'} {destination}"


class TemplateBindingResolver:
    def __init__(self, session: Session):
        self.session = session

    def product_snapshot(self, product: Product, sku: SKU | None) -> dict[str, Any]:
        dimensions = product.dimensions or {}
        unit = str(dimensions.get("unit") or "cm")
        product_values = {
            "name": product.name,
            "material": product.material or "",
            "color": product.color or "",
            "length": self._dimension_value(dimensions.get("length"), unit),
            "width": self._dimension_value(dimensions.get("width"), unit),
            "height": self._dimension_value(dimensions.get("height"), unit),
            "weight": (
                f"{Decimal(str(product.weight_value)).normalize()} {product.weight_unit}"
                if product.weight_value is not None and product.weight_unit
                else ""
            ),
        }
        snapshot: dict[str, Any] = {
            "product": product_values,
            "sku": {"code": sku.code if sku else "", **(sku.attributes if sku else {})},
        }
        for index in range(1, max(3, len(product.selling_points)) + 1):
            snapshot[f"selling_point_{index}"] = (
                product.selling_points[index - 1] if index <= len(product.selling_points) else ""
            )
        return snapshot

    def resolve_text(self, text: str, snapshot: dict[str, Any]) -> str:
        def replace(match: re.Match[str]) -> str:
            path = match.group(1)
            value: Any = snapshot
            for part in path.split("."):
                if not isinstance(value, dict) or part not in value:
                    raise TemplateBindingError(f"unknown template variable {path}")
                value = value[part]
            return str(value)

        return VARIABLE_PATTERN.sub(replace, text)

    def approved_assets(
        self,
        product_id: uuid.UUID,
        requested_sources: set[str],
        explicit: dict[str, uuid.UUID] | None = None,
    ) -> dict[str, AssetVersion]:
        result: dict[str, AssetVersion] = {}
        explicit = explicit or {}
        for source, version_id in explicit.items():
            version = self.session.get(AssetVersion, version_id)
            if (
                version is None
                or version.is_deleted
                or version.status is not AssetStatus.APPROVED
                or version.asset.product_id != product_id
            ):
                raise TemplateBindingError(
                    f"asset binding {source} must reference an APPROVED product asset"
                )
            result[source] = version

        approved = list(
            self.session.scalars(
                select(AssetVersion)
                .join(Asset, AssetVersion.asset_id == Asset.id)
                .where(
                    Asset.product_id == product_id,
                    Asset.is_archived.is_(False),
                    AssetVersion.status == AssetStatus.APPROVED,
                    AssetVersion.is_deleted.is_(False),
                )
                .order_by(AssetVersion.created_at.desc())
            )
        )
        by_type: dict[AssetType, AssetVersion] = {}
        for version in approved:
            by_type.setdefault(version.asset.asset_type, version)

        mapping = {
            "{{asset.cutout}}": [AssetType.CUTOUT, AssetType.MAIN],
            "{{asset.main}}": [AssetType.MAIN, AssetType.CUTOUT],
            "{{asset.closeup}}": [AssetType.CLOSEUP, AssetType.CUTOUT, AssetType.MAIN],
            "{{asset.package}}": [AssetType.PACKAGE, AssetType.CUTOUT, AssetType.MAIN],
        }
        for source in requested_sources:
            if source in result:
                continue
            candidate = next((by_type[kind] for kind in mapping[source] if kind in by_type), None)
            if candidate is None:
                raise TemplateBindingError(f"no APPROVED asset is available for binding {source}")
            result[source] = candidate
        return result

    @staticmethod
    def _dimension_value(value: Any, unit: str) -> str:
        return format_dimension(value, unit) if value is not None else ""
