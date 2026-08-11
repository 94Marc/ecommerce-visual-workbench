import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets.models import Asset, AssetType, AssetVersion
from app.catalog.models import Product
from app.core.config import get_settings
from app.jobs.models import (
    GenerationAttempt,
    GenerationJob,
    GenerationMode,
    JobStatus,
    TaskType,
    ValidationStatus,
)
from app.jobs.providers import (
    get_background_removal_provider,
    get_configured_provider_identity,
    get_image_upscale_provider,
)
from app.jobs.queue import JobDispatcher
from app.jobs.schemas import (
    GenerationJobCreate,
    ImageProcessingTaskCreate,
    VisualPlanGenerationCreate,
)
from app.jobs.workflows import WorkflowRegistry
from app.plans.models import AssetSlot, ProductVisualPlan
from app.rules.models import ImageSlot, Platform, PlatformCode, RuleVersion
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
        if data.visual_plan_id is not None or data.asset_slot_id is not None:
            raise JobStateError("plan and slot jobs must be created through /from-plan")
        if not all((data.platform, data.market, data.category, data.image_slot)):
            raise JobStateError("platform, market, category and image_slot are required")
        source = self._get_original_source(data.source_version_id)
        reference_ids = data.reference_asset_version_ids or [source.id]
        if source.id not in reference_ids:
            reference_ids.insert(0, source.id)
        references = self._get_original_references(reference_ids, source.asset.product_id)
        rule = RuleService(self.session).resolve(
            data.platform, data.market, data.category, data.image_slot
        )
        task = self._manual_task(data, references, rule)
        job = self._new_job(
            data=data,
            rule=rule,
            task=task,
            prompt=self._build_prompt(task),
            references=references,
            generation_mode=data.generation_mode or self._default_mode(data.image_slot),
        )
        self.session.commit()
        self.session.refresh(job)
        self.dispatcher.enqueue(job.id)
        return job

    def create_processing_task(self, data: ImageProcessingTaskCreate) -> GenerationJob:
        source = self.session.get(AssetVersion, data.source_version_id)
        if source is None or source.is_deleted:
            raise JobNotFoundError(f"asset version {data.source_version_id} not found")
        settings = get_settings()
        provider_name, provider_model = self._provider_identity(data.task_type)
        if not data.task_type.is_generation:
            parameters = {
                "upscale_mode": data.upscale_mode.value,
                "tile": data.tile,
                "requested_width": data.width,
                "requested_height": data.height,
            }
            job = GenerationJob(
                source_version_id=source.id,
                resolved_rule_id=None,
                task_type=data.task_type,
                generation_mode=data.generation_mode or GenerationMode.STRICT,
                reference_asset_version_ids=[str(source.id)],
                status=JobStatus.PENDING,
                parameters=parameters,
                provider=provider_name,
                provider_model=provider_model,
                prompt=data.prompt or self._processing_prompt(data.task_type),
                negative_prompt=data.negative_prompt,
                seed=data.seed,
                max_attempts=settings.image_generation_max_attempts,
                timeout_seconds=settings.image_generation_timeout_seconds,
            )
            self.session.add(job)
            self.session.commit()
            self.session.refresh(job)
            self.dispatcher.enqueue(job.id)
            return job

        image_slot = data.image_slot or self._slot_for_task(data.task_type)
        if not all((data.platform, data.market, data.category, image_slot)):
            raise JobStateError(
                "generation tasks require platform, market, category and image_slot"
            )
        reference_ids = list(data.reference_asset_version_ids)
        if source.asset.asset_type is AssetType.ORIGINAL and source.id not in reference_ids:
            reference_ids.insert(0, source.id)
        references = (
            self._get_original_references(reference_ids, source.asset.product_id)
            if reference_ids
            else self._product_original_references(source.asset.product_id)
        )
        source_reference = references[0]
        rule = RuleService(self.session).resolve(
            data.platform, data.market, data.category, image_slot
        )
        workflow = None
        if provider_name == "comfyui" or data.workflow_id is not None:
            workflow = WorkflowRegistry(self.session).resolve(data.task_type, data.workflow_id)
            if workflow.provider != provider_name:
                raise JobStateError(
                    f"workflow provider {workflow.provider} does not match {provider_name}"
                )
        mode = data.generation_mode or self._mode_for_task(data.task_type, image_slot)
        job_data = GenerationJobCreate(
            source_version_id=source_reference.id,
            reference_asset_version_ids=[item.id for item in references],
            platform=data.platform,
            market=data.market,
            category=data.category,
            image_slot=image_slot,
            task_type=data.task_type,
            generation_mode=mode,
            parameters={
                "requested_width": data.width,
                "requested_height": data.height,
            },
        )
        task = self._manual_task(job_data, references, rule)
        if workflow is not None:
            task["workflow"] = {
                "id": str(workflow.id),
                "name": workflow.name,
                "version": workflow.version,
                "file": workflow.workflow_file,
            }
        prompt = data.prompt or self._build_prompt(task)
        job = self._new_job(
            data=job_data,
            rule=rule,
            task=task,
            prompt=prompt,
            references=references,
            generation_mode=mode,
        )
        job.workflow_definition_id = workflow.id if workflow else None
        job.negative_prompt = data.negative_prompt
        job.seed = data.seed
        self.session.commit()
        self.session.refresh(job)
        self.dispatcher.enqueue(job.id)
        return job

    def create_plan_jobs(self, data: VisualPlanGenerationCreate) -> list[GenerationJob]:
        plan = self.session.get(ProductVisualPlan, data.plan_id)
        if plan is None:
            raise JobNotFoundError(f"visual plan {data.plan_id} not found")
        product = self.session.get(Product, plan.product_id)
        platform = self.session.get(Platform, plan.platform_id)
        pinned_rule = self.session.get(RuleVersion, plan.rule_version_id)
        if product is None or platform is None or pinned_rule is None:
            raise JobNotFoundError("visual plan references are incomplete")
        references = self._resolve_plan_references(
            plan, data.reference_asset_version_ids, data.source_version_id
        )
        source = references[0]
        selected = self._select_slots(plan, data.slot_ids)
        jobs: list[GenerationJob] = []
        for slot in selected:
            rule = (
                pinned_rule
                if self._value(pinned_rule.image_slot) == self._value(slot.image_type)
                else RuleService(self.session).resolve(
                    PlatformCode(platform.code),
                    plan.market,
                    plan.category,
                    ImageSlot(self._value(slot.image_type)),
                )
            )
            mode = data.generation_mode or self._default_mode(
                ImageSlot(self._value(slot.image_type))
            )
            task = self._plan_task(product, plan, slot, references, rule, platform, mode)
            job_data = GenerationJobCreate(
                source_version_id=source.id,
                platform=PlatformCode(platform.code),
                market=plan.market,
                category=plan.category,
                image_slot=ImageSlot(self._value(slot.image_type)),
                task_type=self._task_for_slot(ImageSlot(self._value(slot.image_type))),
                generation_mode=mode,
                reference_asset_version_ids=[reference.id for reference in references],
                visual_plan_id=plan.id,
                asset_slot_id=slot.id,
                parameters={"task": task},
            )
            jobs.append(
                self._new_job(
                    data=job_data,
                    rule=rule,
                    task=task,
                    prompt=self._build_prompt(task),
                    references=references,
                    generation_mode=mode,
                )
            )
        self.session.commit()
        for job in jobs:
            self.session.refresh(job)
            self.dispatcher.enqueue(job.id)
        return jobs

    def get_job(self, job_id: uuid.UUID) -> GenerationJob:
        job = self.session.get(GenerationJob, job_id)
        if job is None:
            raise JobNotFoundError(f"generation job {job_id} not found")
        return job

    def list_jobs(
        self, status: JobStatus | None = None, product_id: uuid.UUID | None = None
    ) -> list[GenerationJob]:
        statement = select(GenerationJob)
        if status:
            statement = statement.where(GenerationJob.status == status)
        if product_id:
            statement = statement.join(
                AssetVersion, GenerationJob.source_version_id == AssetVersion.id
            ).join(Asset, AssetVersion.asset_id == Asset.id)
            statement = statement.where(Asset.product_id == product_id)
        return list(self.session.scalars(statement.order_by(GenerationJob.created_at.desc())))

    def list_attempts(self, job_id: uuid.UUID) -> list[GenerationAttempt]:
        self.get_job(job_id)
        return list(
            self.session.scalars(
                select(GenerationAttempt)
                .where(GenerationAttempt.generation_job_id == job_id)
                .order_by(GenerationAttempt.attempt_number)
            )
        )

    def retry_job(self, job_id: uuid.UUID) -> GenerationJob:
        job = self.get_job(job_id)
        if job.status is not JobStatus.FAILED:
            raise JobStateError("only failed jobs can be retried")
        job.status = JobStatus.PENDING
        job.failure_code = None
        job.error_message = None
        job.retryable = False
        job.completed_at = None
        job.duration_ms = None
        job.validation_status = ValidationStatus.PENDING
        job.validation_result = {}
        job.parameters = {
            **job.parameters,
            "manual_retry_count": int(job.parameters.get("manual_retry_count", 0)) + 1,
        }
        self.session.commit()
        self.session.refresh(job)
        self.dispatcher.enqueue(job.id)
        return job

    def regenerate_job(
        self,
        job_id: uuid.UUID,
        feedback: str | None = None,
        reject_reason: str | None = None,
    ) -> GenerationJob:
        parent = self.get_job(job_id)
        if parent.status is not JobStatus.COMPLETED:
            raise JobStateError("only completed jobs can be regenerated")
        reference_ids = [uuid.UUID(item) for item in parent.reference_asset_version_ids]
        if not reference_ids:
            reference_ids = [parent.source_version_id]
        source = self._get_original_source(parent.source_version_id)
        references = self._get_original_references(reference_ids, source.asset.product_id)
        task = dict(parent.parameters.get("task", {}))
        task["references"] = [self._reference_snapshot(item) for item in references]
        task["revision"] = {
            "reject_reason": reject_reason,
            "review_comment": feedback,
            "previous_prompt": parent.revised_prompt or parent.prompt,
        }
        parameters = {**parent.parameters, "task": task, "regenerated_from_job_id": str(parent.id)}
        if feedback:
            parameters["review_feedback"] = feedback
        if reject_reason:
            parameters["reject_reason"] = reject_reason
        provider_name, provider_model = self._provider_identity(parent.task_type)
        revised_prompt = self._build_revised_prompt(
            parent.revised_prompt or parent.prompt, reject_reason, feedback
        )
        job = GenerationJob(
            source_version_id=parent.source_version_id,
            resolved_rule_id=parent.resolved_rule_id,
            visual_plan_id=parent.visual_plan_id,
            asset_slot_id=parent.asset_slot_id,
            parent_job_id=parent.id,
            platform=parent.platform,
            market=parent.market,
            category=parent.category,
            image_slot=parent.image_slot,
            generation_mode=parent.generation_mode,
            task_type=parent.task_type,
            workflow_definition_id=parent.workflow_definition_id,
            reference_asset_version_ids=[str(item.id) for item in references],
            status=JobStatus.PENDING,
            parameters=parameters,
            prompt=parent.prompt,
            revised_prompt=revised_prompt,
            negative_prompt=parent.negative_prompt,
            seed=parent.seed,
            provider=provider_name,
            provider_model=provider_model,
            max_attempts=get_settings().image_generation_max_attempts,
            timeout_seconds=get_settings().image_generation_timeout_seconds,
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        self.dispatcher.enqueue(job.id)
        return job

    def _new_job(
        self,
        *,
        data: GenerationJobCreate,
        rule: RuleVersion,
        task: dict[str, Any],
        prompt: str,
        references: list[AssetVersion],
        generation_mode: GenerationMode,
    ) -> GenerationJob:
        settings = get_settings()
        task_type = data.task_type or self._task_for_slot(data.image_slot)
        provider_name, provider_model = self._provider_identity(task_type)
        parameters = {**data.parameters, "task": task}
        job = GenerationJob(
            **data.model_dump(
                exclude={
                    "parameters",
                    "reference_asset_version_ids",
                    "generation_mode",
                    "task_type",
                }
            ),
            parameters=parameters,
            reference_asset_version_ids=[str(item.id) for item in references],
            generation_mode=generation_mode,
            task_type=task_type,
            resolved_rule_id=rule.id,
            status=JobStatus.PENDING,
            provider=provider_name,
            provider_model=provider_model,
            prompt=prompt,
            max_attempts=settings.image_generation_max_attempts,
            timeout_seconds=settings.image_generation_timeout_seconds,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def _get_original_source(self, version_id: uuid.UUID) -> AssetVersion:
        source = self.session.get(AssetVersion, version_id)
        if source is None or source.is_deleted:
            raise JobNotFoundError(f"asset version {version_id} not found")
        if source.asset.asset_type is not AssetType.ORIGINAL:
            raise JobStateError("generation source must be an immutable ORIGINAL version")
        return source

    def _get_original_references(
        self, version_ids: list[uuid.UUID], product_id: uuid.UUID
    ) -> list[AssetVersion]:
        references: list[AssetVersion] = []
        seen: set[uuid.UUID] = set()
        for version_id in version_ids:
            if version_id in seen:
                continue
            reference = self._get_original_source(version_id)
            if reference.asset.product_id != product_id:
                raise JobStateError("reference image belongs to a different product")
            seen.add(version_id)
            references.append(reference)
        if not references:
            raise JobNotFoundError("at least one ORIGINAL reference image is required")
        return references

    def _resolve_plan_references(
        self,
        plan: ProductVisualPlan,
        reference_ids: list[uuid.UUID] | None,
        source_version_id: uuid.UUID | None,
    ) -> list[AssetVersion]:
        requested = list(reference_ids or [])
        if source_version_id is not None and source_version_id not in requested:
            requested.insert(0, source_version_id)
        if requested:
            return self._get_original_references(requested, plan.product_id)
        references = list(
            self.session.scalars(
            select(AssetVersion)
            .join(Asset, AssetVersion.asset_id == Asset.id)
            .where(
                Asset.product_id == plan.product_id,
                Asset.asset_type == AssetType.ORIGINAL,
                Asset.is_archived.is_(False),
                AssetVersion.is_deleted.is_(False),
            )
                .order_by(Asset.created_at, AssetVersion.created_at.desc())
                .limit(10)
            )
        )
        if not references:
            raise JobNotFoundError("visual plan product has no ORIGINAL source image")
        return references

    def _product_original_references(self, product_id: uuid.UUID) -> list[AssetVersion]:
        references = list(
            self.session.scalars(
                select(AssetVersion)
                .join(Asset, AssetVersion.asset_id == Asset.id)
                .where(
                    Asset.product_id == product_id,
                    Asset.asset_type == AssetType.ORIGINAL,
                    Asset.is_archived.is_(False),
                    AssetVersion.is_deleted.is_(False),
                )
                .order_by(Asset.created_at, AssetVersion.created_at.desc())
                .limit(10)
            )
        )
        if not references:
            raise JobNotFoundError("product has no ORIGINAL reference image")
        return references

    @staticmethod
    def _select_slots(
        plan: ProductVisualPlan, slot_ids: list[uuid.UUID] | None
    ) -> list[AssetSlot]:
        if slot_ids is None:
            return list(plan.slots)
        requested = set(slot_ids)
        selected = [slot for slot in plan.slots if slot.id in requested]
        if len(selected) != len(requested):
            raise JobNotFoundError("one or more asset slots do not belong to the visual plan")
        return selected

    @staticmethod
    def _rule_snapshot(rule: RuleVersion) -> dict[str, Any]:
        return {
            "rule_version_id": str(rule.id),
            "version": rule.version,
            "effective_date": rule.effective_date.isoformat(),
            "image_slot": JobService._value(rule.image_slot),
            "image_type": JobService._value(rule.image_type),
            "min_width": rule.min_width,
            "min_height": rule.min_height,
            "ratio": rule.ratio,
            "max_size": rule.max_size,
            "text_allowed": rule.text_allowed,
            "watermark_allowed": rule.watermark_allowed,
            "extra_constraints": rule.extra_constraints,
        }

    def _manual_task(
        self, data: GenerationJobCreate, references: list[AssetVersion], rule: RuleVersion
    ) -> dict[str, Any]:
        source = references[0]
        mode = data.generation_mode or self._default_mode(data.image_slot)
        product = self.session.get(Product, source.asset.product_id)
        return {
            "schema_version": "1.0",
            "product": self._product_snapshot(product),
            "source": {"asset_version_id": str(source.id), "checksum": source.checksum_sha256},
            "references": [self._reference_snapshot(item) for item in references],
            "platform": data.platform.value,
            "market": data.market,
            "category": data.category,
            "slot": {"id": None, "code": data.image_slot.value, "type": data.image_slot.value},
            "generation_mode": mode.value,
            "rule": self._rule_snapshot(rule),
        }

    def _plan_task(
        self,
        product: Product,
        plan: ProductVisualPlan,
        slot: AssetSlot,
        references: list[AssetVersion],
        rule: RuleVersion,
        platform: Platform,
        mode: GenerationMode,
    ) -> dict[str, Any]:
        source = references[0]
        return {
            "schema_version": "1.0",
            "product": self._product_snapshot(product),
            "source": {"asset_version_id": str(source.id), "checksum": source.checksum_sha256},
            "references": [self._reference_snapshot(item) for item in references],
            "platform": platform.code,
            "market": plan.market,
            "category": plan.category,
            "visual_plan": {"id": str(plan.id), "name": plan.name},
            "slot": {
                "id": str(slot.id),
                "code": slot.code,
                "type": self._value(slot.image_type),
                "label": slot.label,
                "position": slot.position,
            },
            "generation_mode": mode.value,
            "rule": self._rule_snapshot(rule),
        }

    @staticmethod
    def _reference_snapshot(reference: AssetVersion) -> dict[str, Any]:
        return {
            "asset_version_id": str(reference.id),
            "checksum": reference.checksum_sha256,
            "filename": reference.original_filename,
        }

    @staticmethod
    def _product_snapshot(product: Product | None) -> dict[str, Any]:
        if product is None:
            return {}
        return {
            "id": str(product.id),
            "name": product.name,
            "category": product.category,
            "material": product.material,
            "color": product.color,
            "dimensions": product.dimensions,
            "weight": (
                {"value": str(product.weight_value), "unit": product.weight_unit}
                if product.weight_value is not None
                else None
            ),
            "selling_points": product.selling_points,
            "skus": [{"code": sku.code, "attributes": sku.attributes} for sku in product.skus],
        }

    @staticmethod
    def _build_prompt(task: dict[str, Any]) -> str:
        product = task.get("product", {})
        slot = task.get("slot", {})
        rule = task.get("rule", {})
        feedback = task.get("review_feedback")
        mode = task.get("generation_mode", GenerationMode.STRICT.value)
        mode_instruction = {
            GenerationMode.STRICT.value: (
                "STRICT fidelity: do not change product color, shape, texture, logo, "
                "construction, proportions or packaging details."
            ),
            GenerationMode.BALANCED.value: (
                "BALANCED fidelity: background, hands, environment and supporting props may "
                "change, but the product itself must remain maximally consistent."
            ),
            GenerationMode.CREATIVE.value: (
                "CREATIVE composition: allow a stronger marketing atmosphere while keeping the "
                "recognizable product identity and claims truthful."
            ),
        }[mode]
        lines = [
            "Create one production-ready cross-border ecommerce product image.",
            "Use the supplier image as the authoritative product reference. Preserve identity,",
            "shape, material, color, proportions, logos and included parts; "
            "do not invent features.",
            mode_instruction,
            f"Use all {len(task.get('references', [])) or 1} supplied reference angles.",
            f"Product: {product.get('name', '')}; category: {product.get('category', '')}.",
            (
                f"Asset slot: {slot.get('code')} ({slot.get('type')}); purpose: "
                f"{slot.get('label') or 'standard platform listing image'}."
            ),
            f"Platform: {task.get('platform')} / {task.get('market')}.",
            (
                f"Rule: ratio={rule.get('ratio') or 'auto'}, "
                f"min={rule.get('min_width') or 1}x{rule.get('min_height') or 1}px,"
            ),
            (
                f"text_allowed={rule.get('text_allowed')}, "
                f"watermark_allowed={rule.get('watermark_allowed')}."
            ),
            "Return only the final image. Keep the product visually faithful and "
            "commercially clear.",
        ]
        if product.get("selling_points"):
            lines.append("Selling points: " + "; ".join(product["selling_points"]))
        if feedback:
            lines.append(f"Revision feedback: {feedback}")
        return "\n".join(lines)

    @staticmethod
    def _build_revised_prompt(
        previous_prompt: str,
        reject_reason: str | None,
        feedback: str | None,
    ) -> str:
        revision = [previous_prompt, "", "Revision requirements:"]
        if reject_reason:
            revision.append(f"- Reject reason: {reject_reason}")
        if feedback:
            revision.append(f"- Reviewer comment: {feedback}")
        revision.append(
            "Correct only the identified issue and preserve all unaffected product details."
        )
        return "\n".join(revision)

    @staticmethod
    def _default_mode(image_slot: ImageSlot) -> GenerationMode:
        if image_slot in {
            ImageSlot.MAIN,
            ImageSlot.DETAIL,
            ImageSlot.DIMENSION,
            ImageSlot.PACKAGE,
            ImageSlot.CLOSEUP,
        }:
            return GenerationMode.STRICT
        if image_slot in {ImageSlot.SCENE, ImageSlot.USAGE}:
            return GenerationMode.BALANCED
        return GenerationMode.CREATIVE

    @staticmethod
    def _task_for_slot(image_slot: ImageSlot | None) -> TaskType:
        mapping = {
            ImageSlot.MAIN: TaskType.GENERATE_MAIN,
            ImageSlot.SCENE: TaskType.GENERATE_SCENE,
            ImageSlot.USAGE: TaskType.GENERATE_USAGE,
            ImageSlot.DETAIL: TaskType.GENERATE_DETAIL,
            ImageSlot.CLOSEUP: TaskType.GENERATE_DETAIL,
            ImageSlot.DIMENSION: TaskType.GENERATE_DETAIL,
            ImageSlot.PACKAGE: TaskType.GENERATE_DETAIL,
            ImageSlot.COMPARE: TaskType.GENERATE_BACKGROUND,
        }
        if image_slot is None:
            raise JobStateError("image_slot is required for generation")
        return mapping[image_slot]

    @staticmethod
    def _slot_for_task(task_type: TaskType) -> ImageSlot:
        mapping = {
            TaskType.GENERATE_MAIN: ImageSlot.MAIN,
            TaskType.GENERATE_SCENE: ImageSlot.SCENE,
            TaskType.GENERATE_USAGE: ImageSlot.USAGE,
            TaskType.GENERATE_BACKGROUND: ImageSlot.MAIN,
            TaskType.GENERATE_DETAIL: ImageSlot.DETAIL,
        }
        try:
            return mapping[task_type]
        except KeyError as exc:
            raise JobStateError(f"{task_type.value} is not a generation task") from exc

    @classmethod
    def _mode_for_task(cls, task_type: TaskType, image_slot: ImageSlot) -> GenerationMode:
        if task_type is TaskType.GENERATE_BACKGROUND:
            return GenerationMode.CREATIVE
        return cls._default_mode(image_slot)

    @staticmethod
    def _processing_prompt(task_type: TaskType) -> str:
        if task_type is TaskType.REMOVE_BACKGROUND:
            return "Remove only the background and preserve every product pixel and edge."
        if task_type is TaskType.UPSCALE:
            return (
                "Upscale conservatively; avoid oversharpening, hallucinated texture, "
                "logo changes, and geometry changes."
            )
        raise JobStateError(f"unsupported processing task {task_type.value}")

    @staticmethod
    def _provider_identity(task_type: TaskType) -> tuple[str, str]:
        if task_type is TaskType.REMOVE_BACKGROUND:
            provider = get_background_removal_provider()
            return provider.name, provider.model
        if task_type is TaskType.UPSCALE:
            provider = get_image_upscale_provider()
            return provider.name, provider.model
        return get_configured_provider_identity()

    @staticmethod
    def _value(value: Any) -> str:
        return value.value if hasattr(value, "value") else str(value)
