import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets.models import Asset, AssetType, AssetVersion
from app.catalog.models import Product
from app.core.config import get_settings
from app.jobs.models import GenerationAttempt, GenerationJob, JobStatus, ValidationStatus
from app.jobs.providers import get_configured_provider_identity
from app.jobs.queue import JobDispatcher
from app.jobs.schemas import GenerationJobCreate, VisualPlanGenerationCreate
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
        source = self._get_original_source(data.source_version_id)
        rule = RuleService(self.session).resolve(
            data.platform, data.market, data.category, data.image_slot
        )
        task = self._manual_task(data, source, rule)
        job = self._new_job(
            data=data,
            rule=rule,
            task=task,
            prompt=self._build_prompt(task),
        )
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
        source = self._resolve_plan_source(plan, data.source_version_id)
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
            task = self._plan_task(product, plan, slot, source, rule, platform)
            job_data = GenerationJobCreate(
                source_version_id=source.id,
                platform=PlatformCode(platform.code),
                market=plan.market,
                category=plan.category,
                image_slot=ImageSlot(self._value(slot.image_type)),
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

    def list_jobs(self, status: JobStatus | None = None) -> list[GenerationJob]:
        statement = select(GenerationJob)
        if status:
            statement = statement.where(GenerationJob.status == status)
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

    def regenerate_job(self, job_id: uuid.UUID, feedback: str | None = None) -> GenerationJob:
        parent = self.get_job(job_id)
        if parent.status is not JobStatus.COMPLETED:
            raise JobStateError("only completed jobs can be regenerated")
        task = dict(parent.parameters.get("task", {}))
        if feedback:
            task["review_feedback"] = feedback
        parameters = {**parent.parameters, "task": task, "regenerated_from_job_id": str(parent.id)}
        if feedback:
            parameters["review_feedback"] = feedback
        provider_name, provider_model = get_configured_provider_identity()
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
            status=JobStatus.PENDING,
            parameters=parameters,
            prompt=self._build_prompt(task),
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
    ) -> GenerationJob:
        settings = get_settings()
        provider_name, provider_model = get_configured_provider_identity(settings)
        parameters = {**data.parameters, "task": task}
        job = GenerationJob(
            **data.model_dump(exclude={"parameters"}),
            parameters=parameters,
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

    def _resolve_plan_source(
        self, plan: ProductVisualPlan, source_version_id: uuid.UUID | None
    ) -> AssetVersion:
        if source_version_id is not None:
            source = self._get_original_source(source_version_id)
            if source.asset.product_id != plan.product_id:
                raise JobStateError("source image belongs to a different product")
            return source
        source = self.session.scalar(
            select(AssetVersion)
            .join(Asset, AssetVersion.asset_id == Asset.id)
            .where(
                Asset.product_id == plan.product_id,
                Asset.asset_type == AssetType.ORIGINAL,
                Asset.is_archived.is_(False),
                AssetVersion.is_deleted.is_(False),
            )
            .order_by(AssetVersion.created_at.desc())
            .limit(1)
        )
        if source is None:
            raise JobNotFoundError("visual plan product has no ORIGINAL source image")
        return source

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
        self, data: GenerationJobCreate, source: AssetVersion, rule: RuleVersion
    ) -> dict[str, Any]:
        product = self.session.get(Product, source.asset.product_id)
        return {
            "schema_version": "1.0",
            "product": self._product_snapshot(product),
            "source": {"asset_version_id": str(source.id), "checksum": source.checksum_sha256},
            "platform": data.platform.value,
            "market": data.market,
            "category": data.category,
            "slot": {"id": None, "code": data.image_slot.value, "type": data.image_slot.value},
            "rule": self._rule_snapshot(rule),
        }

    def _plan_task(
        self,
        product: Product,
        plan: ProductVisualPlan,
        slot: AssetSlot,
        source: AssetVersion,
        rule: RuleVersion,
        platform: Platform,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "product": self._product_snapshot(product),
            "source": {"asset_version_id": str(source.id), "checksum": source.checksum_sha256},
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
            "rule": self._rule_snapshot(rule),
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
        lines = [
            "Create one production-ready cross-border ecommerce product image.",
            "Use the supplier image as the authoritative product reference. Preserve identity,",
            "shape, material, color, proportions, logos and included parts; "
            "do not invent features.",
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
    def _value(value: Any) -> str:
        return value.value if hasattr(value, "value") else str(value)
