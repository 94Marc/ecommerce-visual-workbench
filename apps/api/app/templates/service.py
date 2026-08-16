from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.assets.models import Asset, AssetStatus, AssetType, AssetVersion, ContentKind
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
from app.templates.bindings import (
    VARIABLE_PATTERN,
    TemplateBindingError,
    TemplateBindingResolver,
)
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
    NON_PRODUCTION_DATA_SOURCES = {
        "DEMO_TEST_DATA",
        "PLACEHOLDER",
        "UNKNOWN",
        "MISSING_SOURCE",
    }
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
        TemplateType.SELLING_POINT: AssetType.DETAIL,
        TemplateType.PARAMETER: AssetType.DETAIL,
        TemplateType.PACKAGE: AssetType.PACKAGE,
        TemplateType.COMPARE: AssetType.COMPARE,
    }
    TYPE_TO_CONTENT_KIND = {
        TemplateType.DETAIL: ContentKind.CLOSEUP,
        TemplateType.SELLING_POINT: ContentKind.SELLING_POINT,
        TemplateType.PARAMETER: ContentKind.PARAMETER,
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
        provenance = self._data_provenance(product, sku, document.layers, snapshot)
        snapshot = {**snapshot, **provenance}
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
                "data_source": provenance["data_source"],
                "contains_demo_data": provenance["contains_demo_data"],
                "demo_data_fields": provenance["demo_data_fields"],
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
                subject_fill_ratio=data.subject_fill_ratio,
                edge_cleanup=data.edge_cleanup,
                tone_correction=data.tone_correction,
            )
            output = self._persist_output(
                data, version, source, rendered, provenance
            )
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
            "content_kind": (
                output.asset.content_kind.value if output.asset.content_kind else None
            ),
            "data_source": provenance["data_source"],
            "contains_demo_data": provenance["contains_demo_data"],
            "demo_data_fields": provenance["demo_data_fields"],
            "render_postprocessing": rendered.metadata,
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

    def _persist_output(
        self,
        data,
        version,
        source,
        rendered,
        provenance: dict[str, Any],
    ) -> AssetVersion:
        assets = AssetService(self.session, self.storage)
        asset_type = self.TYPE_TO_ASSET[version.template.template_type]
        content_kind = self.TYPE_TO_CONTENT_KIND.get(version.template.template_type)
        existing = None
        if data.asset_slot_id:
            slot = self.session.get(AssetSlot, data.asset_slot_id)
            if slot is None or slot.plan.product_id != data.product_id:
                raise TemplateInvariantError("asset slot does not belong to the product")
            if slot.template_id and slot.template_id != version.template_id:
                raise TemplateInvariantError("asset slot is bound to a different template")
            existing = self.session.scalar(select(Asset).where(Asset.asset_slot_id == slot.id))
            asset_type = AssetType(self._value(slot.image_type))
        if asset_type is not AssetType.DETAIL:
            content_kind = None
        if existing:
            if existing.content_kind not in {None, content_kind}:
                raise TemplateInvariantError(
                    "existing asset content_kind does not match the selected template"
                )
            existing.content_kind = content_kind
            return assets.append_processed_version(
                existing.id,
                source.id,
                rendered.content,
                rendered.filename,
                rendered.mime_type,
                status=AssetStatus.REVIEW,
                width=rendered.width,
                height=rendered.height,
                contains_demo_data=provenance["contains_demo_data"],
                demo_data_fields=provenance["demo_data_fields"],
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
            content_kind=content_kind,
            contains_demo_data=provenance["contains_demo_data"],
            demo_data_fields=provenance["demo_data_fields"],
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

    @classmethod
    def _data_provenance(
        cls,
        product: Product,
        sku: SKU | None,
        layers,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        bound_fields = cls._text_bindings(layers)
        demo_fields: set[str] = set()
        data_sources: set[str] = set()
        dimensions = product.dimensions or {}
        sku_attributes = sku.attributes if sku else {}

        global_sources = {
            str(value).upper()
            for value in (
                dimensions.get("data_source"),
                sku_attributes.get("data_source"),
            )
            if value
        }
        blocked_global = global_sources & cls.NON_PRODUCTION_DATA_SOURCES
        if blocked_global:
            data_sources.update(blocked_global)
            demo_fields.update(bound_fields)

        measurement_source = str(dimensions.get("measurement_source") or "").upper()
        if measurement_source in cls.NON_PRODUCTION_DATA_SOURCES:
            data_sources.add(measurement_source)
            demo_fields.update(
                bound_fields & {"product.length", "product.width", "product.height"}
            )

        for path in bound_fields:
            value = cls._snapshot_value(snapshot, path)
            marker = str(value).upper() if value is not None else ""
            if marker in cls.NON_PRODUCTION_DATA_SOURCES:
                data_sources.add(marker)
                demo_fields.add(path)

        ordered_sources = sorted(data_sources)
        return {
            "data_source": ordered_sources[0] if ordered_sources else None,
            "data_sources": ordered_sources,
            "contains_demo_data": bool(demo_fields),
            "demo_data_fields": sorted(demo_fields),
        }

    @classmethod
    def _text_bindings(cls, layers) -> set[str]:
        result: set[str] = set()
        for layer in layers:
            if layer.visible and layer.type is LayerType.TEXT and layer.text:
                result.update(VARIABLE_PATTERN.findall(layer.text))
            if layer.children:
                result.update(cls._text_bindings(layer.children))
        return result

    @staticmethod
    def _snapshot_value(snapshot: dict[str, Any], path: str) -> Any:
        value: Any = snapshot
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                return None
            value = value[part]
        return value

    @staticmethod
    def _value(value) -> str:
        return value.value if hasattr(value, "value") else str(value)
