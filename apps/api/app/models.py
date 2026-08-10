"""Import all ORM models so metadata and migrations discover them."""

from app.assets.models import Asset, AssetVersion
from app.catalog.models import SKU, Product

__all__ = ["Asset", "AssetVersion", "Product", "SKU"]
