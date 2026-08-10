import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.assets.models import AssetType, AssetVersion
from app.assets.service import AssetService
from app.assets.storage import ObjectStorage
from app.core.models import utc_now
from app.jobs.models import GenerationJob, JobStatus
from app.jobs.service import JobNotFoundError, JobStateError


@dataclass(frozen=True)
class GenerationOutput:
    content: bytes
    filename: str
    mime_type: str


class GenerationProvider(Protocol):
    def generate(self, job: GenerationJob, source: bytes) -> GenerationOutput: ...


class MockGenerationProvider:
    """Deterministic V1 provider; makes no external AI calls."""

    def generate(self, job: GenerationJob, source: bytes) -> GenerationOutput:
        marker = f"MOCK:{job.platform}:{job.image_slot}:".encode()
        return GenerationOutput(
            content=marker + source,
            filename=f"{job.image_slot.value.lower()}-{job.id}.mock",
            mime_type="application/x-workbench-mock-image",
        )


class GenerationWorker:
    def __init__(
        self,
        session: Session,
        storage: ObjectStorage,
        provider: GenerationProvider | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.provider = provider or MockGenerationProvider()

    def process(self, job_id: uuid.UUID) -> GenerationJob:
        job = self.session.get(GenerationJob, job_id)
        if job is None:
            raise JobNotFoundError(f"generation job {job_id} not found")
        if job.status is JobStatus.COMPLETED:
            return job
        if job.status is not JobStatus.PENDING:
            raise JobStateError(f"cannot process job in {job.status} state")

        job.status = JobStatus.PROCESSING
        job.started_at = utc_now()
        self.session.commit()

        try:
            source = self.session.get(AssetVersion, job.source_version_id)
            if source is None:
                raise JobNotFoundError(f"asset version {job.source_version_id} not found")
            source_bytes = self.storage.get(source.object_key)
            output = self.provider.generate(job, source_bytes)
            derived = AssetService(self.session, self.storage).create_derived(
                source.id,
                AssetType(job.image_slot.value),
                output.content,
                output.filename,
                output.mime_type,
                label=f"{job.platform.value} {job.image_slot.value}",
            )
            job.output_version_id = derived.versions[-1].id
            job.status = JobStatus.COMPLETED
            job.completed_at = utc_now()
            job.error_message = None
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            job = self.session.get(GenerationJob, job_id)
            if job is None:
                raise
            job.status = JobStatus.FAILED
            job.completed_at = utc_now()
            job.error_message = str(exc)[:1000]
            self.session.commit()
        self.session.refresh(job)
        return job
