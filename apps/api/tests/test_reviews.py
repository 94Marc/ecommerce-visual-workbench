import uuid
from datetime import date

import pytest
from app.assets.models import AssetStatus, AssetVersion
from app.assets.service import AssetService
from app.catalog.schemas import ProductCreate
from app.catalog.service import CatalogService
from app.jobs.models import JobStatus
from app.jobs.schemas import GenerationJobCreate
from app.jobs.service import JobService
from app.jobs.worker import GenerationWorker
from app.reviews.models import ReviewDecision
from app.reviews.schemas import ReviewCreate, ReviewUpdate
from app.reviews.service import ReviewInvariantError, ReviewNotFoundError, ReviewService
from app.rules.models import ImageSlot, PlatformCode
from app.rules.schemas import PlatformRuleCreate
from app.rules.service import RuleService

from tests.conftest import MemoryJobDispatcher, MemoryObjectStorage


def completed_output(session, storage, dispatcher):
    product = CatalogService(session).create_product(
        ProductCreate(name="Organizer", category="home")
    )
    source = (
        AssetService(session, storage)
        .create_original(product.id, b"raw", "organizer.jpg", "image/jpeg")
        .versions[0]
    )
    RuleService(session).create_rule(
        PlatformRuleCreate(
            platform=PlatformCode.TEMU,
            market="US",
            category="home",
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
            category="home",
            image_slot=ImageSlot.MAIN,
        )
    )
    return GenerationWorker(session, storage).process(job.id).output_version_id, source


def test_approve_generated_version(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    output_id, _ = completed_output(session, storage, dispatcher)

    result = ReviewService(session, dispatcher).decide(
        output_id,
        ReviewCreate(decision=ReviewDecision.APPROVED, reviewer="Mina"),
    )

    assert result.review.decision is ReviewDecision.APPROVED
    assert result.regenerated_job is None
    assert session.get(AssetVersion, output_id).status is AssetStatus.APPROVED


def test_regenerate_creates_new_pending_job_from_original_source(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    output_id, source = completed_output(session, storage, dispatcher)

    result = ReviewService(session, dispatcher).decide(
        output_id,
        ReviewCreate(
            decision=ReviewDecision.REGENERATE,
            reviewer="Mina",
            comment="Product is too small in frame",
        ),
    )

    assert result.regenerated_job.status is JobStatus.PENDING
    assert result.regenerated_job.source_version_id == source.id
    assert result.regenerated_job.parameters["regenerated_from_review_id"] == str(result.review.id)


def test_original_asset_cannot_be_reviewed(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    _, source = completed_output(session, storage, dispatcher)

    with pytest.raises(ReviewInvariantError, match="completed generation outputs"):
        ReviewService(session, dispatcher).decide(
            source.id,
            ReviewCreate(decision=ReviewDecision.REJECTED, reviewer="Mina"),
        )


def test_review_crud_updates_version_status_and_soft_deletes(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    output_id, _ = completed_output(session, storage, dispatcher)
    reviews = ReviewService(session, dispatcher)
    result = reviews.decide(
        output_id,
        ReviewCreate(
            decision=ReviewDecision.REJECTED,
            reviewer="Mina",
            comment="Shadow is too strong",
        ),
    )

    assert session.get(AssetVersion, output_id).status is AssetStatus.REJECTED
    assert reviews.get_review(result.review.id).id == result.review.id
    edited = reviews.update_review(
        result.review.id, ReviewUpdate(comment="Reduce shadow and preserve texture")
    )
    assert edited.comment == "Reduce shadow and preserve texture"

    reviews.delete_review(result.review.id)
    assert reviews.list_reviews(output_id) == []
    assert session.get(AssetVersion, output_id).status is AssetStatus.REVIEW


def test_review_lookup_is_scoped_to_asset_version(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    output_id, _ = completed_output(session, storage, dispatcher)
    reviews = ReviewService(session, dispatcher)
    result = reviews.decide(
        output_id,
        ReviewCreate(decision=ReviewDecision.REJECTED, reviewer="Mina"),
    )

    with pytest.raises(ReviewNotFoundError):
        reviews.get_review(result.review.id, uuid.uuid4())
