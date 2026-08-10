import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.assets.storage import ObjectStorage, get_object_storage
from app.core.database import get_session
from app.exports.schemas import ExportCreate, ExportRead
from app.exports.service import ExportInvariantError, ExportNotFoundError, ExportService

router = APIRouter(prefix="/exports", tags=["exports"])


def service(
    session: Session = Depends(get_session), storage: ObjectStorage = Depends(get_object_storage)
) -> ExportService:
    return ExportService(session, storage)


@router.post("", response_model=ExportRead, status_code=status.HTTP_201_CREATED)
def create_export(data: ExportCreate, exports: ExportService = Depends(service)):
    try:
        return exports.create_bundle(data)
    except ExportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExportInvariantError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{bundle_id}", response_model=ExportRead)
def get_export(bundle_id: uuid.UUID, exports: ExportService = Depends(service)):
    try:
        return exports.get_bundle(bundle_id)
    except ExportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{bundle_id}/download")
def download_export(bundle_id: uuid.UUID, exports: ExportService = Depends(service)):
    try:
        bundle, content = exports.download(bundle_id)
    except ExportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    filename = f"{bundle.platform.value}-{bundle.product_id}.zip"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
