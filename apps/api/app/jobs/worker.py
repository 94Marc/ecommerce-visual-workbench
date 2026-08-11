import secrets
import uuid
from collections.abc import Callable
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
    GenerationQualityCheck,
    JobStatus,
    TaskType,
    ValidationStatus,
    WorkflowDefinition,
)
from app.jobs.providers import (
    BackgroundRemovalProvider,
    ImageGenerationProvider,
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageProviderError,
    ImageTransformationRequest,
    ImageUpscaleProvider,
    ReferenceImage,
    get_background_removal_provider,
    get_image_generation_provider,
    get_image_upscale_provider,
)
from app.jobs.quality import GenerationQualityEvaluator
from app.jobs.service import JobNotFoundError, JobStateError
from app.rules.models import RuleVersion

GenerationProvider = ImageGenerationProvider


class GenerationWorker:
    def __init__(
        self,
        session: Session,
        storage: ObjectStorage,
        provider: ImageGenerationProvider | None = None,
        quality_evaluator: GenerationQualityEvaluator | None = None,
        background_provider: BackgroundRemovalProvider | None = None,
        upscale_provider: ImageUpscaleProvider | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.generation_provider = provider or get_image_generation_provider()
        self.background_provider = background_provider or get_background_removal_provider()
        self.upscale_provider = upscale_provider or get_image_upscale_provider()
        self.provider = self.generation_provider
        self.quality_evaluator = quality_evaluator or GenerationQualityEvaluator()

    def process(self, job_id: uuid.UUID) -> GenerationJob:
        job = self.session.get(GenerationJob, job_id)
        if job is None:
            raise JobNotFoundError(f"generation job {job_id} not found")
        if job.status is JobStatus.COMPLETED:
            return job
        if job.status is not JobStatus.PENDING:
            raise JobStateError(f"cannot process job in {job.status} state")

        provider = self._provider_for(job.task_type)
        job.status = JobStatus.PROCESSING
        job.started_at = utc_now()
        job.completed_at = None
        job.duration_ms = None
        job.provider = provider.name
        job.provider_model = provider.model
        self.session.commit()

        try:
            source = self.session.get(AssetVersion, job.source_version_id)
            if source is None or source.is_deleted:
                raise JobNotFoundError(f"asset version {job.source_version_id} not found")
            rule = (
                self.session.get(RuleVersion, job.resolved_rule_id)
                if job.resolved_rule_id
                else None
            )
            if job.task_type.is_generation and rule is None:
                raise JobNotFoundError("generation task has no resolved rule version")
            references = self._load_references(job, require_original=job.task_type.is_generation)
            action = self._build_action(job, provider, references, rule)
            output = self._run_attempts(job, provider.name, provider.model, action)
            if output is not None:
                self._persist_and_validate(job, source, rule, output, references)
        except Exception as exc:
            self.session.rollback()
            job = self.session.get(GenerationJob, job_id)
            if job is None:
                raise
            if isinstance(exc, ImageProviderError):
                self._fail_job(job, exc.code, str(exc), exc.retryable)
            else:
                self._fail_job(job, "worker_error", str(exc), False)
        self.session.refresh(job)
        return job

    def _provider_for(
        self, task_type: TaskType
    ) -> ImageGenerationProvider | BackgroundRemovalProvider | ImageUpscaleProvider:
        if task_type is TaskType.REMOVE_BACKGROUND:
            return self.background_provider
        if task_type is TaskType.UPSCALE:
            return self.upscale_provider
        return self.generation_provider

    def _build_action(
        self,
        job: GenerationJob,
        provider: ImageGenerationProvider | BackgroundRemovalProvider | ImageUpscaleProvider,
        references: tuple[ReferenceImage, ...],
        rule: RuleVersion | None,
    ) -> Callable[[], ImageGenerationResult]:
        if job.task_type is TaskType.REMOVE_BACKGROUND:
            request = self._transformation_request(job, references[0])
            return lambda: provider.remove_background(request)  # type: ignore[union-attr]
        if job.task_type is TaskType.UPSCALE:
            request = self._transformation_request(job, references[0])
            return lambda: provider.upscale(request)  # type: ignore[union-attr]
        if rule is None:
            raise JobNotFoundError("generation task has no resolved rule")
        request = self._generation_request(job, references, rule)
        return lambda: provider.generate(request)  # type: ignore[union-attr]

    def _run_attempts(
        self,
        job: GenerationJob,
        provider_name: str,
        provider_model: str,
        action: Callable[[], ImageGenerationResult],
    ) -> ImageGenerationResult | None:
        for cycle_attempt in range(1, job.max_attempts + 1):
            attempt_number = job.attempt_count + 1
            attempt = GenerationAttempt(
                generation_job_id=job.id,
                attempt_number=attempt_number,
                status=AttemptStatus.PROCESSING,
                provider=provider_name,
                provider_model=provider_model,
                started_at=utc_now(),
            )
            self.session.add(attempt)
            self.session.commit()
            try:
                output = self._inspect_output(action())
            except ImageProviderError as exc:
                self._record_attempt_failure(job, attempt, attempt_number, exc)
                if exc.retryable and cycle_attempt < job.max_attempts:
                    continue
                self._fail_job(job, exc.code, str(exc), exc.retryable)
                return None
            except Exception as exc:
                wrapped = ImageProviderError(
                    str(exc), code="provider_error", retryable=False
                )
                self._record_attempt_failure(job, attempt, attempt_number, wrapped)
                self._fail_job(job, wrapped.code, str(wrapped), wrapped.retryable)
                return None

            job.attempt_count = attempt_number
            job.provider_request_id = output.provider_request_id
            attempt.status = AttemptStatus.COMPLETED
            attempt.completed_at = utc_now()
            attempt.duration_ms = self._duration_ms(attempt.started_at, attempt.completed_at)
            attempt.provider_request_id = output.provider_request_id
            self.session.commit()
            return output
        return None

    def _record_attempt_failure(
        self,
        job: GenerationJob,
        attempt: GenerationAttempt,
        attempt_number: int,
        error: ImageProviderError,
    ) -> None:
        job.attempt_count = attempt_number
        attempt.status = AttemptStatus.FAILED
        attempt.completed_at = utc_now()
        attempt.duration_ms = self._duration_ms(attempt.started_at, attempt.completed_at)
        attempt.provider_request_id = error.request_id
        attempt.failure_code = error.code
        attempt.retryable = error.retryable
        attempt.error_message = str(error)[:1000]
        job.provider_request_id = error.request_id
        self.session.commit()

    def _persist_and_validate(
        self,
        job: GenerationJob,
        source: AssetVersion,
        rule: RuleVersion | None,
        output: ImageGenerationResult,
        references: tuple[ReferenceImage, ...],
    ) -> None:
        version = self._persist_output(job, source, output)
        job.output_version_id = version.id
        job.output_metadata = {
            **output.metadata,
            "provider": job.provider,
            "provider_model": job.provider_model,
            "source_asset_version_id": str(source.id),
            "source_width": source.width,
            "source_height": source.height,
            "output_width": output.width,
            "output_height": output.height,
            "mime_type": output.mime_type,
            "byte_size": len(output.content),
        }

        if job.task_type.is_generation:
            if rule is None:
                raise JobNotFoundError("generation output cannot be validated without a rule")
            result = self.quality_evaluator.evaluate(rule, output, references)
            quality = GenerationQualityCheck(
                generation_job_id=job.id,
                output_version_id=version.id,
                product_similarity=result.product_similarity,
                resolution=result.resolution,
                aspect_ratio=result.aspect_ratio,
                file_size=result.file_size,
                format=result.format,
                text_risk=result.text_risk,
                watermark_risk=result.watermark_risk,
                review_required=result.review_required,
            )
            self.session.add(quality)
            failed = [
                name
                for name, check in {
                    "resolution": result.resolution,
                    "aspect_ratio": result.aspect_ratio,
                    "file_size": result.file_size,
                    "format": result.format,
                }.items()
                if check["status"] == "failed"
            ]
            job.validation_status = (
                ValidationStatus.PASSED
                if result.measurable_checks_passed
                else ValidationStatus.FAILED
            )
            job.validation_result = {"valid": not failed, "violations": failed}
            if failed:
                version.status = AssetStatus.REJECTED
        else:
            job.validation_status = ValidationStatus.PASSED
            job.validation_result = {"valid": True, "violations": []}

        job.status = JobStatus.COMPLETED
        job.completed_at = utc_now()
        job.duration_ms = self._duration_ms(job.started_at, job.completed_at)
        job.failure_code = None
        job.error_message = None
        job.retryable = False
        job.output_metadata = {**job.output_metadata, "duration_ms": job.duration_ms}
        self.session.commit()

    def _persist_output(
        self, job: GenerationJob, source: AssetVersion, output: ImageGenerationResult
    ) -> AssetVersion:
        assets = AssetService(self.session, self.storage)
        if job.task_type is TaskType.REMOVE_BACKGROUND:
            derived = assets.create_derived(
                source.id,
                AssetType.CUTOUT,
                output.content,
                output.filename,
                output.mime_type,
                width=output.width,
                height=output.height,
                label="透明背景抠图",
            )
            return derived.versions[-1]
        if job.task_type is TaskType.UPSCALE:
            if source.asset.asset_type is AssetType.ORIGINAL:
                derived = assets.create_derived(
                    source.id,
                    AssetType.CLOSEUP,
                    output.content,
                    output.filename,
                    output.mime_type,
                    width=output.width,
                    height=output.height,
                    label="高清增强",
                )
                return derived.versions[-1]
            return assets.append_processed_version(
                source.asset_id,
                source.id,
                output.content,
                output.filename,
                output.mime_type,
                status=AssetStatus.REVIEW,
                width=output.width,
                height=output.height,
            )

        existing = None
        if job.asset_slot_id is not None:
            existing = self.session.scalar(
                select(Asset).where(Asset.asset_slot_id == job.asset_slot_id)
            )
        if existing is None:
            if job.image_slot is None or job.platform is None:
                raise JobStateError("generation output is missing platform slot metadata")
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
            return derived.versions[-1]
        return assets.append_processed_version(
            existing.id,
            source.id,
            output.content,
            output.filename,
            output.mime_type,
            status=AssetStatus.REVIEW,
            width=output.width,
            height=output.height,
        )

    def _load_references(
        self, job: GenerationJob, *, require_original: bool
    ) -> tuple[ReferenceImage, ...]:
        raw_ids = job.reference_asset_version_ids or [str(job.source_version_id)]
        references: list[ReferenceImage] = []
        for raw_id in raw_ids:
            version = self.session.get(AssetVersion, uuid.UUID(str(raw_id)))
            if version is None or version.is_deleted:
                raise JobNotFoundError(f"reference asset version {raw_id} is unavailable")
            if require_original and version.asset.asset_type is not AssetType.ORIGINAL:
                raise JobStateError("generation references must be immutable ORIGINAL versions")
            references.append(
                ReferenceImage(
                    asset_version_id=str(version.id),
                    content=self.storage.get(version.object_key),
                    filename=version.original_filename,
                    mime_type=version.mime_type,
                )
            )
        return tuple(references)

    def _generation_request(
        self,
        job: GenerationJob,
        references: tuple[ReferenceImage, ...],
        rule: RuleVersion,
    ) -> ImageGenerationRequest:
        size, width, height = self._target_size(rule)
        requested_width = job.parameters.get("requested_width")
        requested_height = job.parameters.get("requested_height")
        if requested_width and requested_height:
            width, height = int(requested_width), int(requested_height)
            size = f"{width}x{height}"
        settings = get_settings()
        workflow = (
            self.session.get(WorkflowDefinition, job.workflow_definition_id)
            if job.workflow_definition_id
            else None
        )
        if job.seed is None:
            job.seed = secrets.randbits(63)
            self.session.commit()
        workflow_parameters = dict(workflow.default_parameters) if workflow else {}
        workflow_parameters.update(job.parameters.get("workflow_parameters", {}))
        return ImageGenerationRequest(
            job_id=str(job.id),
            prompt=job.revised_prompt or job.prompt,
            references=references,
            size=size,
            width=width,
            height=height,
            quality=settings.image_generation_quality,
            output_format=settings.image_generation_output_format,
            timeout_seconds=job.timeout_seconds,
            workflow_id=str(workflow.id) if workflow else None,
            workflow_file=workflow.workflow_file if workflow else None,
            negative_prompt=job.negative_prompt,
            generation_mode=job.generation_mode.value,
            seed=job.seed,
            workflow_parameters=workflow_parameters,
        )

    @staticmethod
    def _transformation_request(
        job: GenerationJob, source: ReferenceImage
    ) -> ImageTransformationRequest:
        return ImageTransformationRequest(
            job_id=str(job.id),
            source=source,
            timeout_seconds=job.timeout_seconds,
            mode=str(job.parameters.get("upscale_mode") or "CONSERVATIVE"),
            tile=job.parameters.get("tile"),
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
        job.duration_ms = self._duration_ms(job.started_at, job.completed_at)
        job.failure_code = code[:80]
        job.error_message = message[:1000]
        job.retryable = retryable
        self.session.commit()

    @staticmethod
    def _duration_ms(started_at, completed_at) -> int | None:
        if started_at is None or completed_at is None:
            return None
        return max(0, int((completed_at - started_at).total_seconds() * 1000))
