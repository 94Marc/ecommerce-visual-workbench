"""Import all ORM models so metadata and migrations discover them."""

from app.catalog.models import SKU, Product

__all__ = ["Product", "SKU"]
