import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.assets.schemas import AssetRead
from app.assets.service import AssetInvariantError, AssetNotFoundError, AssetService
from app.assets.storage import ObjectStorage, get_object_storage
from app.core.database import get_session

router = APIRouter(tags=["assets"])


def service(
    session: Session = Depends(get_session), storage: ObjectStorage = Depends(get_object_storage)
) -> AssetService:
    return AssetService(session, storage)


@router.post(
    "/products/{product_id}/assets/original",
    response_model=AssetRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_original(
    product_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    sku_id: Annotated[uuid.UUID | None, Form()] = None,
    label: Annotated[str | None, Form()] = None,
    assets: AssetService = Depends(service),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="image file is empty")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="only image uploads are accepted")
    try:
        return assets.create_original(
            product_id,
            content,
            file.filename or "original.bin",
            file.content_type or "application/octet-stream",
            sku_id=sku_id,
            label=label,
        )
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AssetInvariantError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/products/{product_id}/assets", response_model=list[AssetRead])
def list_assets(product_id: uuid.UUID, assets: AssetService = Depends(service)):
    return assets.list_product_assets(product_id)


@router.get("/assets/{asset_id}", response_model=AssetRead)
def get_asset(asset_id: uuid.UUID, assets: AssetService = Depends(service)):
    try:
        return assets.get_asset(asset_id)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

