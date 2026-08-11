import uuid
from dataclasses import replace
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets.models import Asset, AssetStatus, AssetType, AssetVersion
from app.assets.service import AssetService
from app.assets.storage import ObjectStorage
from app.core.config import get_settings
from app.core.models import utc_now
from app.jobs.models import (
    AttemptStatus,
    GenerationAttempt,
    GenerationJob,
    JobStatus,
    ValidationStatus,
)
from app.jobs.providers import (
    ImageGenerationProvider,
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageProviderError,
    get_image_generation_provider,
)
from app.jobs.service import JobNotFoundError, JobStateError
from app.rules.models import RuleVersion
from app.rules.schemas import ImageProbe
from app.rules.service import RuleService

GenerationProvider = ImageGenerationProvider


class GenerationWorker:
    def __init__(
        self,
        session: Session,
        storage: ObjectStorage,
        provider: ImageGenerationProvider | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.provider = provider or get_image_generation_provider()

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
        job.completed_at = None
        job.provider = self.provider.name
        job.provider_model = self.provider.model
        self.session.commit()

        try:
            source = self.session.get(AssetVersion, job.source_version_id)
            rule = self.session.get(RuleVersion, job.resolved_rule_id)
            if source is None:
                raise JobNotFoundError(f"asset version {job.source_version_id} not found")
            if rule is None:
                raise JobNotFoundError(f"rule version {job.resolved_rule_id} not found")
            source_bytes = self.storage.get(source.object_key)
            request = self._request(job, source, source_bytes, rule)
            output = self._run_attempts(job, request)
            if output is not None:
                self._persist_and_validate(job, source, rule, output)
        except Exception as exc:
            self.session.rollback()
            job = self.session.get(GenerationJob, job_id)
            if job is None:
                raise
            self._fail_job(job, "worker_error", str(exc), False)
        self.session.refresh(job)
        return job

    def _run_attempts(
        self, job: GenerationJob, request: ImageGenerationRequest
    ) -> ImageGenerationResult | None:
        for cycle_attempt in range(1, job.max_attempts + 1):
            attempt_number = job.attempt_count + 1
            attempt = GenerationAttempt(
                generation_job_id=job.id,
                attempt_number=attempt_number,
                status=AttemptStatus.PROCESSING,
                provider=self.provider.name,
                provider_model=self.provider.model,
                started_at=utc_now(),
            )
            self.session.add(attempt)
            self.session.commit()
            try:
                output = self.provider.generate(request)
                output = self._inspect_output(output)
            except ImageProviderError as exc:
                job.attempt_count = attempt_number
                attempt.status = AttemptStatus.FAILED
                attempt.completed_at = utc_now()
                attempt.provider_request_id = exc.request_id
                attempt.failure_code = exc.code
                attempt.retryable = exc.retryable
                attempt.error_message = str(exc)[:1000]
                job.provider_request_id = exc.request_id
                self.session.commit()
                if exc.retryable and cycle_attempt < job.max_attempts:
                    continue
                self._fail_job(job, exc.code, str(exc), exc.retryable)
                return None
            except Exception as exc:
                job.attempt_count = attempt_number
                attempt.status = AttemptStatus.FAILED
                attempt.completed_at = utc_now()
                attempt.failure_code = "provider_error"
                attempt.error_message = str(exc)[:1000]
                self.session.commit()
                self._fail_job(job, "provider_error", str(exc), False)
                return None

            job.attempt_count = attempt_number
            job.provider_request_id = output.provider_request_id
            attempt.status = AttemptStatus.COMPLETED
            attempt.completed_at = utc_now()
            attempt.provider_request_id = output.provider_request_id
            self.session.commit()
            return output
        return None

    def _persist_and_validate(
        self,
        job: GenerationJob,
        source: AssetVersion,
        rule: RuleVersion,
        output: ImageGenerationResult,
    ) -> None:
        assets = AssetService(self.session, self.storage)
        existing = None
        if job.asset_slot_id is not None:
            existing = self.session.scalar(
                select(Asset).where(Asset.asset_slot_id == job.asset_slot_id)
            )
        if existing is None:
            derived = assets.create_derived(
                source.id,
                AssetType(job.image_slot.value),
                output.content,
                output.filename,
                output.mime_type,
                width=output.width,
                height=output.height,
                label=f"{job.platform.value} {job.image_slot.value}",
                asset_slot_id=job.asset_slot_id,
            )
            version = derived.versions[-1]
        else:
            version = assets.append_processed_version(
                existing.id,
                source.id,
                output.content,
                output.filename,
                output.mime_type,
                status=AssetStatus.REVIEW,
                width=output.width,
                height=output.height,
            )

        validation = RuleService(self.session).validate_image(
            rule,
            ImageProbe(
                width=output.width,
                height=output.height,
                mime_type=output.mime_type,
                byte_size=len(output.content),
                has_text=output.has_text,
                has_watermark=output.has_watermark,
            ),
        )
        job.output_version_id = version.id
        job.validation_status = (
            ValidationStatus.PASSED if validation.valid else ValidationStatus.FAILED
        )
        job.validation_result = validation.model_dump()
        job.status = JobStatus.COMPLETED
        job.completed_at = utc_now()
        job.failure_code = None
        job.error_message = None
        job.retryable = False
        if not validation.valid:
            version.status = AssetStatus.REJECTED
        self.session.commit()

    def _request(
        self,
        job: GenerationJob,
        source: AssetVersion,
        source_bytes: bytes,
        rule: RuleVersion,
    ) -> ImageGenerationRequest:
        size, width, height = self._target_size(rule)
        settings = get_settings()
        return ImageGenerationRequest(
            job_id=str(job.id),
            prompt=job.prompt,
            source=source_bytes,
            source_filename=source.original_filename,
            source_mime_type=source.mime_type,
            size=size,
            width=width,
            height=height,
            quality=settings.image_generation_quality,
            output_format=settings.image_generation_output_format,
            timeout_seconds=job.timeout_seconds,
        )

    @staticmethod
    def _inspect_output(output: ImageGenerationResult) -> ImageGenerationResult:
        try:
            with Image.open(BytesIO(output.content)) as image:
                width, height = image.size
                detected_format = (image.format or "").lower()
        except (UnidentifiedImageError, OSError) as exc:
            raise ImageProviderError(
                "provider output is not a readable image",
                code="invalid_image",
                retryable=False,
                request_id=output.provider_request_id,
            ) from exc
        mime_type = "image/jpeg" if detected_format == "jpeg" else f"image/{detected_format}"
        return replace(output, width=width, height=height, mime_type=mime_type)

    @staticmethod
    def _target_size(rule: RuleVersion) -> tuple[str, int, int]:
        ratio = 1.0
        if rule.ratio:
            width, height = rule.ratio.split(":", 1)
            ratio = float(width) / float(height)
        if ratio >= 1.2:
            return "1536x1024", 1536, 1024
        if ratio <= 0.83:
            return "1024x1536", 1024, 1536
        return "1024x1024", 1024, 1024

    def _fail_job(
        self, job: GenerationJob, code: str, message: str, retryable: bool
    ) -> None:
        job.status = JobStatus.FAILED
        job.completed_at = utc_now()
        job.failure_code = code[:80]
        job.error_message = message[:1000]
        job.retryable = retryable
        self.session.commit()
