import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.assets.storage import ObjectStorage, get_object_storage
from app.core.database import get_session
from app.jobs.models import JobStatus
from app.jobs.queue import JobDispatcher, get_job_dispatcher
from app.jobs.schemas import GenerationJobCreate, GenerationJobRead
from app.jobs.service import JobNotFoundError, JobService
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


@router.post("/{job_id}/simulate", response_model=GenerationJobRead)
def simulate_job(
    job_id: uuid.UUID,
    session: Session = Depends(get_session),
    storage: ObjectStorage = Depends(get_object_storage),
):
    """Development-only endpoint that executes the V1 mock provider synchronously."""
    try:
        return GenerationWorker(session, storage).process(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
