import io
import json
import zipfile
from datetime import date

import pytest
from app.assets.service import AssetService
from app.catalog.schemas import ProductCreate
from app.catalog.service import CatalogService
from app.exports.schemas import ExportCreate
from app.exports.service import ExportInvariantError, ExportService
from app.jobs.schemas import GenerationJobCreate
from app.jobs.service import JobService
from app.jobs.worker import GenerationWorker
from app.reviews.models import ReviewDecision
from app.reviews.schemas import ReviewCreate
from app.reviews.service import ReviewService
from app.rules.models import ImageSlot, PlatformCode
from app.rules.schemas import PlatformRuleCreate
from app.rules.service import RuleService

from tests.conftest import MemoryJobDispatcher, MemoryObjectStorage


def generated_scope(session, storage, dispatcher):
    product = CatalogService(session).create_product(
        ProductCreate(name="Packing cubes", category="travel")
    )
    source = (
        AssetService(session, storage)
        .create_original(product.id, b"supplier", "cubes.jpg", "image/jpeg")
        .versions[0]
    )
    RuleService(session).create_rule(
        PlatformRuleCreate(
            platform=PlatformCode.TEMU,
            market="US",
            category="travel",
            image_slot=ImageSlot.MAIN,
            rule_version="1.0.0",
            effective_date=date(2026, 1, 1),
        )
    )
    job = JobService(session, dispatcher).create_job(
        GenerationJobCreate(
            source_version_id=source.id,
            platform=PlatformCode.TEMU,
            market="US",
            category="travel",
            image_slot=ImageSlot.MAIN,
        )
    )
    completed = GenerationWorker(session, storage).process(job.id)
    return product, completed.output_version_id


def test_export_contains_only_approved_assets_and_manifest(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    product, output_id = generated_scope(session, storage, dispatcher)
    ReviewService(session, dispatcher).decide(
        output_id,
        ReviewCreate(decision=ReviewDecision.APPROVED, reviewer="Kai"),
    )

    bundle = ExportService(session, storage).create_bundle(
        ExportCreate(
            product_id=product.id,
            platform=PlatformCode.TEMU,
            market="US",
            category="travel",
        )
    )

    archive_bytes = storage.get(bundle.object_key)
    assert bundle.checksum_sha256
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["platform"] == "temu"
        assert len(manifest["files"]) == 1
        assert manifest["files"][0]["asset_version_id"] == str(output_id)
        assert manifest["files"][0]["filename"] in names


def test_export_rejects_scope_without_approved_assets(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    product, _ = generated_scope(session, storage, dispatcher)

    with pytest.raises(ExportInvariantError, match="no approved"):
        ExportService(session, storage).create_bundle(
            ExportCreate(
                product_id=product.id,
                platform=PlatformCode.TEMU,
                market="US",
                category="travel",
            )
        )
