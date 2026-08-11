from __future__ import annotations

import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.assets.models import Asset, AssetStatus, AssetType, AssetVersion
from app.assets.service import AssetService
from app.assets.storage import ObjectStorage
from app.catalog.models import SKU, Product
from app.core.models import utc_now
from app.jobs.models import (
    AttemptStatus,
    GenerationAttempt,
    GenerationJob,
    GenerationMode,
    JobStatus,
    ProviderType,
    TaskType,
    ValidationStatus,
)
from app.plans.models import AssetSlot
from app.rules.models import ImageSlot, Platform, PlatformCode, RuleVersion
from app.rules.schemas import ImageProbe
from app.rules.service import RuleNotFoundError, RuleService
from app.templates.bindings import TemplateBindingError, TemplateBindingResolver
from app.templates.demos import DEMO_TEMPLATES
from app.templates.models import (
    Template,
    TemplateRenderRecord,
    TemplateStatus,
    TemplateType,
    TemplateVersion,
)
from app.templates.renderer import DeterministicTemplateRenderer
from app.templates.schema_types import LayerType, TemplateDocument, validate_template_schema
from app.templates.schemas import (
    TemplateCreate,
    TemplateRenderCreate,
    TemplateUpdate,
    TemplateVersionInput,
)


class TemplateNotFoundError(LookupError):
    pass


class TemplateInvariantError(ValueError):
    pass


class TemplateCodeConflictError(ValueError):
    pass


class TemplateService:
    def __init__(self, session: Session):
        self.session = session

    def ensure_demos(self) -> None:
        existing = set(self.session.scalars(select(Template.code)))
        changed = False
        for definition in DEMO_TEMPLATES:
            if definition["code"] in existing:
                continue
            template = Template(
                id=uuid.UUID(definition["id"]),
                name=definition["name"],
                code=definition["code"],
                template_type=definition["template_type"],
                status=definition["status"],
            )
            template.versions.append(
                TemplateVersion(
                    version=1,
                    canvas_width=definition["canvas_width"],
                    canvas_height=definition["canvas_height"],
                    background=definition["background"],
                    schema_json=validate_template_schema(definition["schema_json"]),
                )
            )
            self.session.add(template)
            changed = True
        if changed:
            self.session.commit()

    def create(self, data: TemplateCreate) -> Template:
        if self.session.scalar(select(Template.id).where(Template.code == data.code)):
            raise TemplateCodeConflictError(f"template code {data.code} already exists")
        template = Template(
            **data.model_dump(
                exclude={"canvas_width", "canvas_height", "background", "schema_json"}
            )
        )
        template.versions.append(
            TemplateVersion(
                version=1,
                canvas_width=data.canvas_width,
                canvas_height=data.canvas_height,
                background=data.background,
                schema_json=validate_template_schema(data.schema_json),
            )
        )
        self.session.add(template)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise TemplateCodeConflictError(f"template code {data.code} already exists") from exc
        self.session.refresh(template)
        return template

    def list(
        self,
        template_type: TemplateType | None = None,
        status: TemplateStatus | None = None,
    ) -> list[Template]:
        self.ensure_demos()
        statement = select(Template)
        if template_type:
            statement = statement.where(Template.template_type == template_type)
        if status:
            statement = statement.where(Template.status == status)
        return list(self.session.scalars(statement.order_by(Template.code)))

    def get(self, template_id: uuid.UUID) -> Template:
        self.ensure_demos()
        template = self.session.get(Template, template_id)
        if template is None:
            raise TemplateNotFoundError(f"template {template_id} not found")
        return template

    def update(self, template_id: uuid.UUID, data: TemplateUpdate) -> Template:
        template = self.get(template_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(template, key, value)
        self.session.commit()
        self.session.refresh(template)
        return template

    def archive(self, template_id: uuid.UUID) -> Template:
        return self.update(template_id, TemplateUpdate(status=TemplateStatus.ARCHIVED))

    def create_version(self, template_id: uuid.UUID, data: TemplateVersionInput) -> TemplateVersion:
        template = self.get(template_id)
        next_version = (
            self.session.scalar(
                select(func.coalesce(func.max(TemplateVersion.version), 0)).where(
                    TemplateVersion.template_id == template.id
                )
            )
            + 1
        )
        version = TemplateVersion(
            template_id=template.id,
            version=next_version,
            canvas_width=data.canvas_width,
            canvas_height=data.canvas_height,
            background=data.background,
            schema_json=validate_template_schema(data.schema_json),
        )
        self.session.add(version)
        self.session.commit()
        self.session.refresh(version)
        return version

    def list_versions(self, template_id: uuid.UUID) -> list[TemplateVersion]:
        self.get(template_id)
        return list(
            self.session.scalars(
                select(TemplateVersion)
                .where(TemplateVersion.template_id == template_id)
                .order_by(TemplateVersion.version.desc())
            )
        )

    def get_version(self, template_id: uuid.UUID, version_id: uuid.UUID) -> TemplateVersion:
        version = self.session.get(TemplateVersion, version_id)
        if version is None or version.template_id != template_id:
            raise TemplateNotFoundError(f"template version {version_id} not found")
        return version

    def copy(self, template_id: uuid.UUID, code: str, name: str | None = None) -> Template:
        source = self.get(template_id)
        version = source.latest_version
        if version is None:
            raise TemplateInvariantError("template has no version to copy")
        return self.create(
            TemplateCreate(
                name=name or f"{source.name} 副本",
                code=code,
                template_type=source.template_type,
                status=TemplateStatus.DRAFT,
                canvas_width=version.canvas_width,
                canvas_height=version.canvas_height,
                background=version.background,
                schema_json=version.schema_json,
            )
        )


class TemplateRenderService:
    TYPE_TO_TASK = {
        TemplateType.MAIN: TaskType.RENDER_MAIN_TEMPLATE,
        TemplateType.DIMENSION: TaskType.RENDER_DIMENSION_TEMPLATE,
        TemplateType.DETAIL: TaskType.RENDER_DETAIL_TEMPLATE,
        TemplateType.SELLING_POINT: TaskType.RENDER_SELLING_POINT_TEMPLATE,
        TemplateType.PARAMETER: TaskType.RENDER_PARAMETER_TEMPLATE,
        TemplateType.PACKAGE: TaskType.RENDER_PACKAGE_TEMPLATE,
        TemplateType.COMPARE: TaskType.RENDER_COMPARE_TEMPLATE,
    }
    TYPE_TO_ASSET = {
        TemplateType.MAIN: AssetType.MAIN,
        TemplateType.DIMENSION: AssetType.DIMENSION,
        TemplateType.DETAIL: AssetType.DETAIL,
        TemplateType.SELLING_POINT: AssetType.COMPARE,
        TemplateType.PARAMETER: AssetType.DETAIL,
        TemplateType.PACKAGE: AssetType.PACKAGE,
        TemplateType.COMPARE: AssetType.COMPARE,
    }

    def __init__(self, session: Session, storage: ObjectStorage):
        self.session = session
        self.storage = storage
        self.bindings = TemplateBindingResolver(session)

    def render(self, data: TemplateRenderCreate) -> tuple[GenerationJob, TemplateRenderRecord]:
        version = self.session.get(TemplateVersion, data.template_version_id)
        product = self.session.get(Product, data.product_id)
        if version is None:
            raise TemplateNotFoundError(f"template version {data.template_version_id} not found")
        if product is None:
            raise TemplateNotFoundError(f"product {data.product_id} not found")
        sku = self.session.get(SKU, data.sku_id) if data.sku_id else None
        if sku is not None and sku.product_id != product.id:
            raise TemplateInvariantError("SKU must belong to the rendered product")
        document = TemplateDocument.model_validate(version.schema_json)
        slot, platform, rule, rule_warning = self._platform_context(data)
        sources = self._image_sources(document.layers)
        assets = self.bindings.approved_assets(product.id, sources, data.asset_bindings)
        if not assets:
            raise TemplateBindingError("template rendering requires at least one APPROVED image")
        source_versions = list({item.id: item for item in assets.values()}.values())
        source = source_versions[0]
        snapshot = self.bindings.product_snapshot(product, sku)
        task_type = self.TYPE_TO_TASK[version.template.template_type]
        started_at = utc_now()
        job = GenerationJob(
            source_version_id=source.id,
            resolved_rule_id=rule.id if rule else None,
            visual_plan_id=slot.product_visual_plan_id if slot else None,
            asset_slot_id=data.asset_slot_id,
            platform=PlatformCode(platform.code) if platform else None,
            market=slot.plan.market if slot else None,
            category=slot.plan.category if slot else None,
            image_slot=(ImageSlot(self._value(slot.image_type)) if slot else None),
            task_type=task_type,
            generation_mode=GenerationMode.STRICT,
            reference_asset_version_ids=[str(item.id) for item in source_versions],
            status=JobStatus.PROCESSING,
            parameters={
                "template_id": str(version.template_id),
                "template_version_id": str(version.id),
                "output_format": data.output_format,
            },
            provider="template",
            provider_type=ProviderType.TEMPLATE,
            provider_model="pillow-konva-schema-v1",
            prompt="",
            attempt_count=1,
            max_attempts=1,
            timeout_seconds=120,
            started_at=started_at,
        )
        self.session.add(job)
        self.session.flush()
        attempt = GenerationAttempt(
            generation_job_id=job.id,
            attempt_number=1,
            status=AttemptStatus.PROCESSING,
            provider="template",
            provider_model="pillow-konva-schema-v1",
            started_at=started_at,
        )
        self.session.add(attempt)
        self.session.commit()

        started = time.perf_counter()
        try:
            rendered = DeterministicTemplateRenderer(self.storage, self.bindings).render(
                version,
                snapshot,
                assets,
                output_format=data.output_format,
                quality=data.quality,
            )
            output = self._persist_output(data, version, source, rendered)
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.failure_code = "template_render_error"
            job.error_message = str(exc)[:1000]
            job.completed_at = utc_now()
            job.duration_ms = max(0, round((time.perf_counter() - started) * 1000))
            attempt.status = AttemptStatus.FAILED
            attempt.failure_code = job.failure_code
            attempt.error_message = job.error_message
            attempt.completed_at = job.completed_at
            attempt.duration_ms = job.duration_ms
            self.session.commit()
            raise

        completed_at = utc_now()
        duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        request_id = f"template-{job.id}"
        job.output_version_id = output.id
        job.provider_request_id = request_id
        job.status = JobStatus.COMPLETED
        if rule is not None:
            result = RuleService(self.session).validate_image(
                rule,
                ImageProbe(
                    width=rendered.width,
                    height=rendered.height,
                    byte_size=len(rendered.content),
                    mime_type=rendered.mime_type,
                    has_text=self._has_text(document.layers),
                    has_watermark=False,
                ),
            )
            job.validation_status = (
                ValidationStatus.PASSED if result.valid else ValidationStatus.FAILED
            )
            job.validation_result = {
                "valid": result.valid,
                "violations": result.violations,
                "warnings": [],
            }
        else:
            job.validation_status = ValidationStatus.FAILED
            job.validation_result = {
                "valid": False,
                "violations": [],
                "warnings": [rule_warning or "RULE_NOT_CONFIGURED"],
            }
        job.completed_at = completed_at
        job.duration_ms = duration_ms
        job.output_metadata = {
            "template_id": str(version.template_id),
            "template_version_id": str(version.id),
            "canvas_width": rendered.width,
            "canvas_height": rendered.height,
            "mime_type": rendered.mime_type,
            "byte_size": len(rendered.content),
            "source_asset_version_ids": [str(item.id) for item in source_versions],
            "rule_result": job.validation_result,
        }
        attempt.status = AttemptStatus.COMPLETED
        attempt.provider_request_id = request_id
        attempt.completed_at = completed_at
        attempt.duration_ms = duration_ms
        record = TemplateRenderRecord(
            template_id=version.template_id,
            template_version_id=version.id,
            generation_job_id=job.id,
            output_asset_version_id=output.id,
            product_id=product.id,
            sku_id=sku.id if sku else None,
            source_asset_version_ids=[str(item.id) for item in source_versions],
            product_data_snapshot=snapshot,
            rendered_at=completed_at,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(job)
        self.session.refresh(record)
        return job, record

    def _persist_output(self, data, version, source, rendered) -> AssetVersion:
        assets = AssetService(self.session, self.storage)
        asset_type = self.TYPE_TO_ASSET[version.template.template_type]
        existing = None
        if data.asset_slot_id:
            slot = self.session.get(AssetSlot, data.asset_slot_id)
            if slot is None or slot.plan.product_id != data.product_id:
                raise TemplateInvariantError("asset slot does not belong to the product")
            if slot.template_id and slot.template_id != version.template_id:
                raise TemplateInvariantError("asset slot is bound to a different template")
            existing = self.session.scalar(select(Asset).where(Asset.asset_slot_id == slot.id))
            asset_type = AssetType(self._value(slot.image_type))
        if existing:
            return assets.append_processed_version(
                existing.id,
                source.id,
                rendered.content,
                rendered.filename,
                rendered.mime_type,
                status=AssetStatus.REVIEW,
                width=rendered.width,
                height=rendered.height,
            )
        derived = assets.create_derived(
            source.id,
            asset_type,
            rendered.content,
            rendered.filename,
            rendered.mime_type,
            width=rendered.width,
            height=rendered.height,
            status=AssetStatus.REVIEW,
            label=f"{version.template.code} 模板成品",
            asset_slot_id=data.asset_slot_id,
        )
        return derived.versions[-1]

    def _platform_context(
        self, data: TemplateRenderCreate
    ) -> tuple[AssetSlot | None, Platform | None, RuleVersion | None, str | None]:
        if data.asset_slot_id is None:
            return None, None, None, "RULE_NOT_CONFIGURED"
        slot = self.session.get(AssetSlot, data.asset_slot_id)
        if slot is None or slot.plan.product_id != data.product_id:
            raise TemplateInvariantError("asset slot does not belong to the product")
        platform = self.session.get(Platform, slot.plan.platform_id)
        if platform is None:
            return slot, None, None, "RULE_NOT_CONFIGURED"
        image_slot = ImageSlot(self._value(slot.image_type))
        pinned = self.session.get(RuleVersion, slot.plan.rule_version_id)
        if pinned is not None and self._value(pinned.image_slot) == image_slot.value:
            return slot, platform, pinned, None
        try:
            resolved = RuleService(self.session).resolve(
                PlatformCode(platform.code), slot.plan.market, slot.plan.category, image_slot
            )
        except RuleNotFoundError:
            return slot, platform, None, "RULE_NOT_CONFIGURED"
        return slot, platform, resolved, None

    @classmethod
    def _image_sources(cls, layers) -> set[str]:
        result: set[str] = set()
        for layer in layers:
            if layer.type is LayerType.IMAGE and layer.assetSource:
                result.add(layer.assetSource)
            if layer.children:
                result.update(cls._image_sources(layer.children))
        return result

    @classmethod
    def _has_text(cls, layers) -> bool:
        for layer in layers:
            if layer.visible and layer.type is LayerType.TEXT and (layer.text or "").strip():
                return True
            if layer.children and cls._has_text(layer.children):
                return True
        return False

    @staticmethod
    def _value(value) -> str:
        return value.value if hasattr(value, "value") else str(value)
