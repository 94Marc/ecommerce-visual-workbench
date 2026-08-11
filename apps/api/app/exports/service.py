import hashlib
import io
import json
import uuid
import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets.models import Asset, AssetVersion
from app.assets.storage import ObjectStorage
from app.catalog.models import Product
from app.exports.models import ExportBundle, ExportStatus
from app.exports.schemas import ExportCreate
from app.jobs.models import GenerationJob, JobStatus, ValidationStatus
from app.reviews.models import ReviewDecision
from app.reviews.service import ReviewService


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
            if reviews.latest_decision(version.id) is ReviewDecision.APPROVED:
                approved.append((job, version))
        if not approved:
            raise ExportInvariantError("no approved generated assets match this export scope")

        bundle_id = uuid.uuid4()
        manifest_files = []
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for index, (job, version) in enumerate(approved, start=1):
                suffix = Path(version.original_filename).suffix.lower() or ".bin"
                filename = f"{index:02d}_{job.image_slot.value}_{str(version.id)[:8]}{suffix}"
                content = self.storage.get(version.object_key)
                archive.writestr(filename, content)
                manifest_files.append(
                    {
                        "filename": filename,
                        "asset_version_id": str(version.id),
                        "image_slot": job.image_slot.value,
                        "asset_slot_id": str(job.asset_slot_id) if job.asset_slot_id else None,
                        "visual_plan_id": str(job.visual_plan_id) if job.visual_plan_id else None,
                        "rule_version_id": str(job.resolved_rule_id),
                        "checksum_sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
            manifest = {
                "schema_version": "1.0",
                "bundle_id": str(bundle_id),
                "product_id": str(data.product_id),
                "platform": data.platform.value,
                "market": data.market,
                "category": data.category,
                "files": manifest_files,
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
