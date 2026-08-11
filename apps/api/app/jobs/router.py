import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.assets.storage import ObjectStorage, get_object_storage
from app.core.database import get_session
from app.jobs.models import JobStatus
from app.jobs.queue import JobDispatcher, get_job_dispatcher
from app.jobs.schemas import (
    GenerationAttemptRead,
    GenerationJobCreate,
    GenerationJobRead,
    RegenerationCreate,
    VisualPlanGenerationCreate,
)
from app.jobs.service import JobNotFoundError, JobService, JobStateError
from app.jobs.worker import GenerationWorker
from app.rules.service import RuleNotFoundError

router = APIRouter(prefix="/generation-jobs", tags=["generation-jobs"])


def service(
    session: Session = Depends(get_session),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
) -> JobService:
    return JobService(session, dispatcher)


@router.post("", response_model=GenerationJobRead, status_code=status.HTTP_201_CREATED)
def create_job(data: GenerationJobCreate, jobs: JobService = Depends(service)):
    try:
        return jobs.create_job(data)
    except (JobNotFoundError, RuleNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/from-plan", response_model=list[GenerationJobRead], status_code=status.HTTP_201_CREATED
)
def create_jobs_from_plan(
    data: VisualPlanGenerationCreate, jobs: JobService = Depends(service)
):
    try:
        return jobs.create_plan_jobs(data)
    except (JobNotFoundError, RuleNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[GenerationJobRead])
def list_jobs(
    job_status: JobStatus | None = Query(default=None, alias="status"),
    jobs: JobService = Depends(service),
):
    return jobs.list_jobs(job_status)


@router.get("/{job_id}", response_model=GenerationJobRead)
def get_job(job_id: uuid.UUID, jobs: JobService = Depends(service)):
    try:
        return jobs.get_job(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/attempts", response_model=list[GenerationAttemptRead])
def list_attempts(job_id: uuid.UUID, jobs: JobService = Depends(service)):
    try:
        return jobs.list_attempts(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{job_id}/retry", response_model=GenerationJobRead)
def retry_job(job_id: uuid.UUID, jobs: JobService = Depends(service)):
    try:
        return jobs.retry_job(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{job_id}/regenerate", response_model=GenerationJobRead)
def regenerate_job(
    job_id: uuid.UUID,
    data: RegenerationCreate,
    jobs: JobService = Depends(service),
):
    try:
        return jobs.regenerate_job(
            job_id,
            data.feedback,
            data.reject_reason.value if data.reject_reason else None,
        )
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{job_id}/process", response_model=GenerationJobRead)
def process_job(
    job_id: uuid.UUID,
    session: Session = Depends(get_session),
    storage: ObjectStorage = Depends(get_object_storage),
):
    """Development endpoint; uses the configured provider (mock by default)."""
    try:
        return GenerationWorker(session, storage).process(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{job_id}/simulate", response_model=GenerationJobRead, deprecated=True)
def simulate_job(
    job_id: uuid.UUID,
    session: Session = Depends(get_session),
    storage: ObjectStorage = Depends(get_object_storage),
):
    return process_job(job_id, session, storage)
