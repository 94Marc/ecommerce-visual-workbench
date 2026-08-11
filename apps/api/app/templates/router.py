import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.assets.storage import ObjectStorage, get_object_storage
from app.core.database import get_session
from app.templates.models import TemplateStatus, TemplateType
from app.templates.schemas import (
    TemplateCopy,
    TemplateCreate,
    TemplateRead,
    TemplateRenderCreate,
    TemplateRenderRead,
    TemplateUpdate,
    TemplateVersionInput,
    TemplateVersionRead,
)
from app.templates.service import (
    TemplateCodeConflictError,
    TemplateInvariantError,
    TemplateNotFoundError,
    TemplateRenderService,
    TemplateService,
)

router = APIRouter(prefix="/templates", tags=["templates"])


def service(session: Session = Depends(get_session)) -> TemplateService:
    return TemplateService(session)


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(data: TemplateCreate, templates: TemplateService = Depends(service)):
    try:
        return templates.create(data)
    except TemplateCodeConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[TemplateRead])
def list_templates(
    template_type: TemplateType | None = Query(default=None),
    template_status: TemplateStatus | None = Query(default=None, alias="status"),
    templates: TemplateService = Depends(service),
):
    return templates.list(template_type, template_status)


@router.post("/renders", response_model=TemplateRenderRead, status_code=status.HTTP_201_CREATED)
def render_template(
    data: TemplateRenderCreate,
    session: Session = Depends(get_session),
    storage: ObjectStorage = Depends(get_object_storage),
):
    try:
        job, record = TemplateRenderService(session, storage).render(data)
        return TemplateRenderRead(
            job_id=job.id,
            output_asset_version_id=record.output_asset_version_id,
            record=record,
        )
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TemplateInvariantError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{template_id}", response_model=TemplateRead)
def get_template(template_id: uuid.UUID, templates: TemplateService = Depends(service)):
    try:
        return templates.get(template_id)
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{template_id}", response_model=TemplateRead)
def update_template(
    template_id: uuid.UUID,
    data: TemplateUpdate,
    templates: TemplateService = Depends(service),
):
    try:
        return templates.update(template_id, data)
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{template_id}", response_model=TemplateRead)
def archive_template(template_id: uuid.UUID, templates: TemplateService = Depends(service)):
    try:
        return templates.archive(template_id)
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{template_id}/versions",
    response_model=TemplateVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_template_version(
    template_id: uuid.UUID,
    data: TemplateVersionInput,
    templates: TemplateService = Depends(service),
):
    try:
        return templates.create_version(template_id, data)
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{template_id}/versions", response_model=list[TemplateVersionRead])
def list_template_versions(
    template_id: uuid.UUID,
    templates: TemplateService = Depends(service),
):
    try:
        return templates.list_versions(template_id)
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{template_id}/versions/{version_id}", response_model=TemplateVersionRead)
def get_template_version(
    template_id: uuid.UUID,
    version_id: uuid.UUID,
    templates: TemplateService = Depends(service),
):
    try:
        return templates.get_version(template_id, version_id)
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{template_id}/copy", response_model=TemplateRead, status_code=status.HTTP_201_CREATED
)
def copy_template(
    template_id: uuid.UUID,
    data: TemplateCopy,
    templates: TemplateService = Depends(service),
):
    try:
        return templates.copy(template_id, data.code, data.name)
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TemplateCodeConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
