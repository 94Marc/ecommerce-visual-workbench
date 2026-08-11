from datetime import date

from app.assets.models import AssetType
from app.assets.service import AssetService
from app.catalog.schemas import ProductCreate
from app.catalog.service import CatalogService
from app.jobs.models import JobStatus
from app.jobs.schemas import GenerationJobCreate
from app.jobs.service import JobService
from app.jobs.worker import GenerationWorker
from app.rules.models import ImageSlot, PlatformCode
from app.rules.schemas import PlatformRuleCreate
from app.rules.service import RuleService

from tests.conftest import MemoryJobDispatcher, MemoryObjectStorage


def setup_source_and_rule(session, storage):
    product = CatalogService(session).create_product(ProductCreate(name="Mug", category="kitchen"))
    original = AssetService(session, storage).create_original(
        product.id, b"raw-image", "mug.jpg", "image/jpeg"
    )
    RuleService(session).create_rule(
        PlatformRuleCreate(
            platform=PlatformCode.TEMU,
            market="US",
            category="kitchen",
            image_slot=ImageSlot.MAIN,
            rule_version="1.0.0",
            effective_date=date(2026, 1, 1),
            constraints={"min_width": 1000},
        )
    )
    return original.versions[0]


def test_create_job_resolves_rule_and_dispatches(session):
    storage = MemoryObjectStorage()
    source = setup_source_and_rule(session, storage)
    dispatcher = MemoryJobDispatcher()

    job = JobService(session, dispatcher).create_job(
        GenerationJobCreate(
            source_version_id=source.id,
            platform=PlatformCode.TEMU,
            market="US",
            category="kitchen",
            image_slot=ImageSlot.MAIN,
        )
    )

    assert job.status is JobStatus.PENDING
    assert dispatcher.job_ids == [job.id]
    assert job.resolved_rule_id is not None


def test_mock_worker_completes_job_with_derived_version(session):
    storage = MemoryObjectStorage()
    source = setup_source_and_rule(session, storage)
    job = JobService(session, MemoryJobDispatcher()).create_job(
        GenerationJobCreate(
            source_version_id=source.id,
            platform=PlatformCode.TEMU,
            market="US",
            category="kitchen",
            image_slot=ImageSlot.MAIN,
        )
    )

    completed = GenerationWorker(session, storage).process(job.id)

    assert completed.status is JobStatus.COMPLETED
    assert completed.output_version_id is not None
    output = session.get(type(source), completed.output_version_id)
    assert output.source_version_id == source.id
    assert output.asset.asset_type is AssetType.MAIN
    assert storage.get(output.object_key).startswith(b"\x89PNG")
    assert completed.provider == "mock"


def test_completed_job_is_idempotent(session):
    storage = MemoryObjectStorage()
    source = setup_source_and_rule(session, storage)
    job = JobService(session, MemoryJobDispatcher()).create_job(
        GenerationJobCreate(
            source_version_id=source.id,
            platform=PlatformCode.TEMU,
            market="US",
            category="kitchen",
            image_slot=ImageSlot.MAIN,
        )
    )
    worker = GenerationWorker(session, storage)
    first = worker.process(job.id)
    first_output = first.output_version_id

    assert worker.process(job.id).output_version_id == first_output
