import hashlib
import io
import json
import uuid
import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets.models import Asset, AssetStatus, AssetType, AssetVersion
from app.assets.storage import ObjectStorage
from app.catalog.models import Product
from app.exports.models import ExportBundle, ExportStatus
from app.exports.schemas import ExportCreate
from app.jobs.models import GenerationJob, JobStatus, ValidationStatus
from app.plans.models import ProductVisualPlan
from app.reviews.models import ReviewDecision
from app.reviews.service import ReviewService
from app.rules.models import ImageSlot, Platform, PlatformCode
from app.rules.service import RuleNotFoundError, RuleService


class ExportNotFoundError(LookupError):
    pass


class ExportInvariantError(ValueError):
    pass


class ExportService:
    def __init__(self, session: Session, storage: ObjectStorage):
        self.session = session
        self.storage = storage

    def create_bundle(self, data: ExportCreate) -> ExportBundle:
        product = self.session.get(Product, data.product_id)
        if product is None:
            raise ExportNotFoundError(f"product {data.product_id} not found")

        jobs = list(
            self.session.scalars(
                select(GenerationJob)
                .where(
                    GenerationJob.platform == data.platform,
                    GenerationJob.market == data.market,
                    GenerationJob.category == data.category,
                    GenerationJob.status == JobStatus.COMPLETED,
                    GenerationJob.validation_status == ValidationStatus.PASSED,
                    GenerationJob.output_version_id.is_not(None),
                )
                .order_by(GenerationJob.image_slot, GenerationJob.completed_at)
            )
        )
        approved: list[tuple[GenerationJob, AssetVersion]] = []
        reviews = ReviewService(self.session, _NoopDispatcher())
        for job in jobs:
            version = self.session.get(AssetVersion, job.output_version_id)
            if version is None:
                continue
            asset = self.session.get(Asset, version.asset_id)
            if asset is None or asset.product_id != data.product_id:
                continue
            if (
                version.status is AssetStatus.APPROVED
                and reviews.latest_decision(version.id) is ReviewDecision.APPROVED
            ):
                approved.append((job, version))
        if not approved:
            raise ExportInvariantError("no approved generated assets match this export scope")

        bundle_id = uuid.uuid4()
        sku = sorted(product.skus, key=lambda item: item.code)[0] if product.skus else None
        root = sku.code if sku else str(product.id)
        manifest_files = []
        exported_slot_ids = {job.asset_slot_id for job, _ in approved if job.asset_slot_id}
        plan_id = next((job.visual_plan_id for job, _ in approved if job.visual_plan_id), None)
        missing_slots = self._missing_slots(plan_id, exported_slot_ids, data.product_id)
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for directory in ("main", "detail", "dimension", "scene", "usage", "package"):
                archive.writestr(f"{root}/{directory}/", b"")
            for index, (job, version) in enumerate(approved, start=1):
                suffix = Path(version.original_filename).suffix.lower() or ".bin"
                slot_name = job.image_slot.value.lower()
                filename = (
                    f"{root}/{slot_name}/{index:02d}_{version.asset.asset_type.value.lower()}_"
                    f"{str(version.id)[:8]}{suffix}"
                )
                content = self.storage.get(version.object_key)
                archive.writestr(filename, content)
                manifest_files.append(
                    {
                        "filename": filename,
                        "asset_id": str(version.asset_id),
                        "asset_version_id": str(version.id),
                        "asset_type": version.asset.asset_type.value,
                        "image_slot": job.image_slot.value,
                        "asset_slot_id": str(job.asset_slot_id) if job.asset_slot_id else None,
                        "visual_plan_id": str(job.visual_plan_id) if job.visual_plan_id else None,
                        "template_provider": {
                            "type": job.provider_type.value,
                            "provider": job.provider,
                            "template_id": job.parameters.get("template_id"),
                            "template_version_id": job.parameters.get("template_version_id"),
                        },
                        "review_status": "APPROVED",
                        "rule_result": {
                            "status": "passed",
                            "rule_version_id": str(job.resolved_rule_id),
                            "validation": job.validation_result,
                        },
                        "checksum_sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
            manifest = {
                "schema_version": "2.0",
                "bundle_id": str(bundle_id),
                "product": {
                    "id": str(product.id),
                    "name": product.name,
                    "category": product.category,
                    "color": product.color,
                    "dimensions": product.dimensions,
                },
                "sku": {"id": str(sku.id), "code": sku.code} if sku else None,
                "platform": data.platform.value,
                "market": data.market,
                "category": data.category,
                "files": manifest_files,
                "missing_slots": missing_slots,
            }
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )

        content = archive_buffer.getvalue()
        object_key = f"exports/{data.platform.value}/{data.product_id}/{bundle_id}.zip"
        self.storage.put(object_key, content, "application/zip")
        bundle = ExportBundle(
            id=bundle_id,
            **data.model_dump(),
            object_key=object_key,
            manifest=manifest,
            checksum_sha256=hashlib.sha256(content).hexdigest(),
            status=ExportStatus.READY,
        )
        self.session.add(bundle)
        self.session.commit()
        self.session.refresh(bundle)
        return bundle

    def _missing_slots(
        self,
        plan_id: uuid.UUID | None,
        exported_slot_ids: set[uuid.UUID],
        product_id: uuid.UUID,
    ) -> list[dict[str, str]]:
        if plan_id is None:
            return []
        plan = self.session.get(ProductVisualPlan, plan_id)
        if plan is None:
            return []
        has_package_source = self.session.scalar(
            select(AssetVersion.id)
            .join(Asset, AssetVersion.asset_id == Asset.id)
            .where(
                Asset.product_id == product_id,
                Asset.asset_type == AssetType.PACKAGE,
                Asset.is_archived.is_(False),
                AssetVersion.status == AssetStatus.APPROVED,
                AssetVersion.is_deleted.is_(False),
            )
            .limit(1)
        )
        missing = []
        platform = self.session.get(Platform, plan.platform_id)
        for slot in plan.slots:
            if slot.id in exported_slot_ids:
                continue
            image_type = (
                slot.image_type.value
                if hasattr(slot.image_type, "value")
                else str(slot.image_type)
            )
            reason = (
                "MISSING_SOURCE"
                if image_type == "PACKAGE" and has_package_source is None
                else "NOT_APPROVED_OR_RULE_FAILED"
            )
            if reason != "MISSING_SOURCE" and platform is not None:
                try:
                    RuleService(self.session).resolve(
                        PlatformCode(platform.code),
                        plan.market,
                        plan.category,
                        ImageSlot(image_type),
                    )
                except RuleNotFoundError:
                    reason = "RULE_NOT_CONFIGURED"
            missing.append(
                {
                    "asset_slot_id": str(slot.id),
                    "slot": slot.code,
                    "image_type": image_type,
                    "reason": reason,
                }
            )
        return missing

    def get_bundle(self, bundle_id: uuid.UUID) -> ExportBundle:
        bundle = self.session.get(ExportBundle, bundle_id)
        if bundle is None:
            raise ExportNotFoundError(f"export bundle {bundle_id} not found")
        return bundle

    def download(self, bundle_id: uuid.UUID) -> tuple[ExportBundle, bytes]:
        bundle = self.get_bundle(bundle_id)
        return bundle, self.storage.get(bundle.object_key)


class _NoopDispatcher:
    def enqueue(self, job_id: uuid.UUID) -> None:
        raise RuntimeError("export review lookup must not enqueue jobs")
