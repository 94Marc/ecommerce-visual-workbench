import base64
from datetime import date

import httpx
import pytest
from app.assets.models import Asset, AssetStatus, AssetType, AssetVersion
from app.assets.service import AssetService
from app.assets.storage import get_object_storage
from app.catalog.schemas import ProductCreate
from app.catalog.service import CatalogService
from app.core.config import Settings
from app.jobs.models import JobStatus, ValidationStatus
from app.jobs.providers import (
    ImageProviderError,
    MockImageGenerationProvider,
    OpenAIImageGenerationProvider,
    get_image_generation_provider,
)
from app.jobs.schemas import VisualPlanGenerationCreate
from app.jobs.service import JobService
from app.jobs.worker import GenerationWorker
from app.plans.schemas import ProductVisualPlanCreate
from app.plans.service import VisualPlanService
from app.reviews.models import ReviewDecision
from app.reviews.schemas import ReviewCreate
from app.reviews.service import ReviewInvariantError, ReviewService
from app.rules.models import ImageSlot, PlatformCode
from app.rules.schemas import PlatformRuleCreate
from app.rules.service import RuleService

from tests.conftest import MemoryJobDispatcher, MemoryObjectStorage


def plan_context(session, storage, *, min_width=1000):
    product = CatalogService(session).create_product(
        ProductCreate(
            name="Stainless travel mug",
            category="kitchen",
            material="304 stainless steel",
            color="blue",
            selling_points=["Leak resistant", "Double wall"],
        )
    )
    source = AssetService(session, storage).create_original(
        product.id, b"supplier-image", "mug.jpg", "image/jpeg"
    )
    rule = RuleService(session).create_rule(
        PlatformRuleCreate(
            platform=PlatformCode.TEMU,
            market="US",
            category="kitchen",
            image_slot=ImageSlot.MAIN,
            version="3.0.0",
            effective_date=date(2026, 8, 1),
            min_width=min_width,
            min_height=min_width,
            ratio="1:1",
            text_allowed=False,
            watermark_allowed=False,
        )
    )
    platform = RuleService(session).list_platforms()[0]
    plan = VisualPlanService(session).create(
        ProductVisualPlanCreate(
            product_id=product.id,
            platform_id=platform.id,
            rule_version_id=rule.id,
            name="Temu launch",
            market="US",
            category="kitchen",
            requested_outputs={ImageSlot.MAIN: 2},
        )
    )
    return product, source.versions[0], plan


def test_plan_expands_to_structured_slot_jobs_and_persists_versions(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    product, source, plan = plan_context(session, storage)

    jobs = JobService(session, dispatcher).create_plan_jobs(
        VisualPlanGenerationCreate(plan_id=plan.id, source_version_id=source.id)
    )

    assert len(jobs) == 2
    assert dispatcher.job_ids == [job.id for job in jobs]
    assert jobs[0].parameters["task"]["product"]["name"] == product.name
    assert jobs[0].parameters["task"]["slot"]["code"] == "MAIN_01"
    assert jobs[0].resolved_rule_id == plan.rule_version_id
    completed = GenerationWorker(session, storage).process(jobs[0].id)
    output = session.get(AssetVersion, completed.output_version_id)
    assert completed.validation_status is ValidationStatus.PASSED
    assert output.asset.asset_slot_id == plan.slots[0].id
    assert output.asset.asset_type is AssetType.MAIN


def test_single_slot_regeneration_appends_an_immutable_version(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    _, source, plan = plan_context(session, storage)
    first_job = JobService(session, dispatcher).create_plan_jobs(
        VisualPlanGenerationCreate(
            plan_id=plan.id, source_version_id=source.id, slot_ids=[plan.slots[0].id]
        )
    )[0]
    first = GenerationWorker(session, storage).process(first_job.id)

    regenerated = JobService(session, dispatcher).regenerate_job(
        first.id, "Make the product larger in frame"
    )
    second = GenerationWorker(session, storage).process(regenerated.id)

    first_version = session.get(AssetVersion, first.output_version_id)
    second_version = session.get(AssetVersion, second.output_version_id)
    assert regenerated.parent_job_id == first.id
    assert "larger in frame" in regenerated.prompt
    assert first_version.asset_id == second_version.asset_id
    assert second_version.version_number == first_version.version_number + 1
    assert first_version.source_version_id == source.id
    assert session.get(Asset, first_version.asset_id).asset_slot_id == plan.slots[0].id


class AlwaysTimeoutProvider:
    name = "test"
    model = "timeout"

    def generate(self, request):
        raise ImageProviderError("slow upstream", code="timeout", retryable=True)


def test_retryable_timeout_records_attempts_and_supports_manual_retry(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    _, source, plan = plan_context(session, storage)
    job = JobService(session, dispatcher).create_plan_jobs(
        VisualPlanGenerationCreate(
            plan_id=plan.id, source_version_id=source.id, slot_ids=[plan.slots[0].id]
        )
    )[0]
    job.max_attempts = 2
    session.commit()

    failed = GenerationWorker(session, storage, AlwaysTimeoutProvider()).process(job.id)

    assert failed.status is JobStatus.FAILED
    assert failed.failure_code == "timeout"
    assert failed.retryable is True
    assert failed.attempt_count == 2
    assert len(JobService(session, dispatcher).list_attempts(job.id)) == 2
    retried = JobService(session, dispatcher).retry_job(job.id)
    assert retried.status is JobStatus.PENDING
    assert dispatcher.job_ids[-1] == job.id


def test_rule_failure_is_persisted_and_blocks_approval(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    _, source, plan = plan_context(session, storage, min_width=2000)
    job = JobService(session, dispatcher).create_plan_jobs(
        VisualPlanGenerationCreate(
            plan_id=plan.id, source_version_id=source.id, slot_ids=[plan.slots[0].id]
        )
    )[0]

    completed = GenerationWorker(session, storage).process(job.id)

    assert completed.status is JobStatus.COMPLETED
    assert completed.validation_status is ValidationStatus.FAILED
    assert "width must be at least" in completed.validation_result["violations"][0]
    assert session.get(AssetVersion, completed.output_version_id).status is AssetStatus.REJECTED
    with pytest.raises(ReviewInvariantError, match="must pass"):
        ReviewService(session, dispatcher).decide(
            completed.output_version_id,
            ReviewCreate(decision=ReviewDecision.APPROVED, reviewer="QA"),
        )


def test_provider_factory_falls_back_to_mock_without_key():
    provider = get_image_generation_provider(
        Settings(image_generation_provider="openai", openai_api_key=None)
    )
    assert isinstance(provider, MockImageGenerationProvider)


def test_openai_provider_decodes_image_without_real_network_call():
    from app.jobs.providers import ImageGenerationRequest

    png = MockImageGenerationProvider().generate(
        ImageGenerationRequest(
            job_id="fixture",
            prompt="fixture",
            source=b"source",
            source_filename="source.png",
            source_mime_type="image/png",
            size="1024x1024",
            width=16,
            height=16,
            quality="medium",
            output_format="png",
            timeout_seconds=5,
        )
    ).content

    def handler(request: httpx.Request):
        assert request.url.path == "/v1/images/edits"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            headers={"x-request-id": "req_test"},
            json={"data": [{"b64_json": base64.b64encode(png).decode()}]},
        )

    provider = OpenAIImageGenerationProvider(
        Settings(image_generation_provider="openai", openai_api_key="test-key"),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.generate(
        ImageGenerationRequest(
            job_id="job",
            prompt="preserve product",
            source=b"source",
            source_filename="source.png",
            source_mime_type="image/png",
            size="1024x1024",
            width=1024,
            height=1024,
            quality="medium",
            output_format="png",
            timeout_seconds=5,
        )
    )
    assert result.content == png
    assert result.provider_request_id == "req_test"


def test_generation_pipeline_api_expands_processes_and_regenerates_one_slot(client, session):
    storage = client.app.dependency_overrides[get_object_storage]()
    _, source, plan = plan_context(session, storage)

    created = client.post(
        "/api/v1/generation-jobs/from-plan",
        json={
            "plan_id": str(plan.id),
            "source_version_id": str(source.id),
            "slot_ids": [str(plan.slots[0].id)],
        },
    )
    assert created.status_code == 201
    job = created.json()[0]
    assert job["asset_slot_id"] == str(plan.slots[0].id)
    assert job["parameters"]["task"]["rule"]["rule_version_id"] == str(plan.rule_version_id)

    processed = client.post(f"/api/v1/generation-jobs/{job['id']}/process")
    assert processed.status_code == 200
    assert processed.json()["validation_status"] == "passed"
    attempts = client.get(f"/api/v1/generation-jobs/{job['id']}/attempts")
    assert attempts.status_code == 200
    assert len(attempts.json()) == 1

    regenerated = client.post(
        f"/api/v1/generation-jobs/{job['id']}/regenerate",
        json={"feedback": "Use a tighter crop"},
    )
    assert regenerated.status_code == 200
    assert regenerated.json()["parent_job_id"] == job["id"]
