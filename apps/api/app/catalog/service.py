import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.catalog.models import SKU, Product
from app.catalog.schemas import ProductCreate, ProductUpdate, SKUCreate


class CatalogNotFoundError(LookupError):
    pass


class DuplicateSKUError(ValueError):
    pass


class CatalogService:
    def __init__(self, session: Session):
        self.session = session

    def create_product(self, data: ProductCreate) -> Product:
        values = data.model_dump(exclude={"dimensions"})
        values["dimensions"] = data.dimensions.model_dump(mode="json") if data.dimensions else {}
        product = Product(**values)
        self.session.add(product)
        self.session.commit()
        return self.get_product(product.id)

    def list_products(self) -> list[Product]:
        statement = select(Product).options(selectinload(Product.skus)).order_by(Product.created_at)
        return list(self.session.scalars(statement).unique())

    def get_product(self, product_id: uuid.UUID) -> Product:
        statement = (
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.skus))
        )
        product = self.session.scalar(statement)
        if product is None:
            raise CatalogNotFoundError(f"product {product_id} not found")
        return product

    def update_product(self, product_id: uuid.UUID, data: ProductUpdate) -> Product:
        product = self.get_product(product_id)
        values = data.model_dump(exclude_unset=True, exclude={"dimensions"})
        if "dimensions" in data.model_fields_set:
            values["dimensions"] = (
                data.dimensions.model_dump(mode="json") if data.dimensions else {}
            )
        for field, value in values.items():
            setattr(product, field, value)
        self.session.commit()
        return self.get_product(product.id)

    def add_sku(self, product_id: uuid.UUID, data: SKUCreate) -> SKU:
        self.get_product(product_id)
        sku = SKU(product_id=product_id, **data.model_dump())
        self.session.add(sku)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateSKUError(f"SKU code {data.code} already exists") from exc
        self.session.refresh(sku)
        return sku
