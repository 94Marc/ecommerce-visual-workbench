import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets.models import AssetVersion
from app.jobs.models import GenerationJob, JobStatus
from app.jobs.queue import JobDispatcher
from app.jobs.schemas import GenerationJobCreate
from app.rules.service import RuleService


class JobNotFoundError(LookupError):
    pass


class JobStateError(ValueError):
    pass


class JobService:
    def __init__(self, session: Session, dispatcher: JobDispatcher):
        self.session = session
        self.dispatcher = dispatcher

    def create_job(self, data: GenerationJobCreate) -> GenerationJob:
        if self.session.get(AssetVersion, data.source_version_id) is None:
            raise JobNotFoundError(f"asset version {data.source_version_id} not found")
        rule = RuleService(self.session).resolve(
            data.platform, data.market, data.category, data.image_slot
        )
        job = GenerationJob(**data.model_dump(), resolved_rule_id=rule.id, status=JobStatus.PENDING)
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        self.dispatcher.enqueue(job.id)
        return job

    def get_job(self, job_id: uuid.UUID) -> GenerationJob:
        job = self.session.get(GenerationJob, job_id)
        if job is None:
            raise JobNotFoundError(f"generation job {job_id} not found")
        return job

    def list_jobs(self, status: JobStatus | None = None) -> list[GenerationJob]:
        statement = select(GenerationJob)
        if status:
            statement = statement.where(GenerationJob.status == status)
        return list(self.session.scalars(statement.order_by(GenerationJob.created_at.desc())))
