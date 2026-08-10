import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.catalog.schemas import ProductCreate, ProductRead, ProductUpdate, SKUCreate, SKURead
from app.catalog.service import CatalogNotFoundError, CatalogService, DuplicateSKUError
from app.core.database import get_session

router = APIRouter(prefix="/products", tags=["products"])


def service(session: Session = Depends(get_session)) -> CatalogService:
    return CatalogService(session)


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(data: ProductCreate, catalog: CatalogService = Depends(service)):
    return catalog.create_product(data)


@router.get("", response_model=list[ProductRead])
def list_products(catalog: CatalogService = Depends(service)):
    return catalog.list_products()


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: uuid.UUID, catalog: CatalogService = Depends(service)):
    try:
        return catalog.get_product(product_id)
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: uuid.UUID, data: ProductUpdate, catalog: CatalogService = Depends(service)
):
    try:
        return catalog.update_product(product_id, data)
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{product_id}/skus", response_model=SKURead, status_code=status.HTTP_201_CREATED)
def add_sku(product_id: uuid.UUID, data: SKUCreate, catalog: CatalogService = Depends(service)):
    try:
        return catalog.add_sku(product_id, data)
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DuplicateSKUError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
