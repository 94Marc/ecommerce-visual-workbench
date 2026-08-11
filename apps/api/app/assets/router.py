import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.assets.models import AssetType
from app.assets.schemas import AssetRead, AssetUpdate, AssetVersionRead, AssetVersionUpdate
from app.assets.service import AssetInvariantError, AssetNotFoundError, AssetService
from app.assets.storage import ObjectStorage, get_object_storage
from app.core.database import get_session

router = APIRouter(tags=["assets"])
MAX_IMAGE_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class UploadedImage:
    content: bytes
    mime_type: str
    width: int
    height: int


def service(
    session: Session = Depends(get_session), storage: ObjectStorage = Depends(get_object_storage)
) -> AssetService:
    return AssetService(session, storage)


async def read_image(file: UploadFile) -> UploadedImage:
    content = await file.read(MAX_IMAGE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="image file is empty")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="image file exceeds 25MB limit")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="only image uploads are accepted")
    try:
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
            image_format = image.format or ""
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=415, detail="uploaded content is not a readable image"
        ) from exc
    detected_mime = Image.MIME.get(image_format)
    if not detected_mime:
        raise HTTPException(status_code=415, detail="uploaded image format is not supported")
    return UploadedImage(content=content, mime_type=detected_mime, width=width, height=height)


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
    image = await read_image(file)
    try:
        return assets.create_original(
            product_id,
            image.content,
            file.filename or "original.bin",
            image.mime_type,
            sku_id=sku_id,
            label=label,
            width=image.width,
            height=image.height,
        )
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AssetInvariantError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/products/{product_id}/assets",
    response_model=AssetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_asset(
    product_id: uuid.UUID,
    asset_type: Annotated[AssetType, Form()],
    file: Annotated[UploadFile, File()],
    source_version_id: Annotated[uuid.UUID | None, Form()] = None,
    sku_id: Annotated[uuid.UUID | None, Form()] = None,
    label: Annotated[str | None, Form()] = None,
    assets: AssetService = Depends(service),
):
    image = await read_image(file)
    try:
        if asset_type is AssetType.ORIGINAL:
            return assets.create_original(
                product_id,
                image.content,
                file.filename or "original.bin",
                image.mime_type,
                sku_id=sku_id,
                label=label,
                width=image.width,
                height=image.height,
            )
        if source_version_id is None:
            raise AssetInvariantError("source_version_id is required for processed assets")
        source = assets.get_version(source_version_id)
        if source.asset.product_id != product_id:
            raise AssetInvariantError("source version must belong to the product")
        derived = assets.create_derived(
            source_version_id,
            asset_type,
            image.content,
            file.filename or "processed.bin",
            image.mime_type,
            label=label,
            width=image.width,
            height=image.height,
        )
        return derived
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


@router.patch("/assets/{asset_id}", response_model=AssetRead)
def update_asset(asset_id: uuid.UUID, data: AssetUpdate, assets: AssetService = Depends(service)):
    try:
        current_slot_id = (
            data.asset_slot_id
            if "asset_slot_id" in data.model_fields_set
            else assets.get_asset(asset_id).asset_slot_id
        )
        return assets.update_asset(asset_id, label=data.label, asset_slot_id=current_slot_id)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AssetInvariantError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(asset_id: uuid.UUID, assets: AssetService = Depends(service)):
    try:
        assets.archive_asset(asset_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AssetInvariantError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/assets/{asset_id}/versions", response_model=list[AssetVersionRead])
def list_versions(asset_id: uuid.UUID, assets: AssetService = Depends(service)):
    try:
        return assets.list_versions(asset_id)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/assets/{asset_id}/versions",
    response_model=AssetVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    asset_id: uuid.UUID,
    source_version_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
    assets: AssetService = Depends(service),
):
    image = await read_image(file)
    try:
        return assets.append_processed_version(
            asset_id,
            source_version_id,
            image.content,
            file.filename or "processed.bin",
            image.mime_type,
            width=image.width,
            height=image.height,
        )
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AssetInvariantError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/asset-versions/{version_id}", response_model=AssetVersionRead)
def get_version(version_id: uuid.UUID, assets: AssetService = Depends(service)):
    try:
        return assets.get_version(version_id)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/asset-versions/{version_id}/content")
def get_version_content(version_id: uuid.UUID, assets: AssetService = Depends(service)):
    try:
        version, content = assets.download_version(version_id)
        filename = Path(version.original_filename).name.replace("\r", "").replace("\n", "")
        return StreamingResponse(
            BytesIO(content),
            media_type=version.mime_type,
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
                "ETag": version.checksum_sha256,
            },
        )
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/asset-versions/{version_id}", response_model=AssetVersionRead)
def update_version(
    version_id: uuid.UUID,
    data: AssetVersionUpdate,
    assets: AssetService = Depends(service),
):
    try:
        return assets.update_version_status(version_id, data.status)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AssetInvariantError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/asset-versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_version(version_id: uuid.UUID, assets: AssetService = Depends(service)):
    try:
        assets.delete_version(version_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AssetInvariantError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
