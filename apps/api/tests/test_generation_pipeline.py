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
from app.jobs.models import GenerationMode, JobStatus, ValidationStatus
from app.jobs.providers import (
    ComfyUIImageGenerationProvider,
    ImageGenerationRequest,
    ImageProviderError,
    ImageTransformationRequest,
    MockImageGenerationProvider,
    OpenAIImageGenerationProvider,
    RealESRGANUpscaleProvider,
    ReferenceImage,
    RembgBackgroundRemovalProvider,
    get_image_generation_provider,
)
from app.jobs.quality import AnalyzerResult, GenerationQualityEvaluator
from app.jobs.schemas import GenerationJobCreate, VisualPlanGenerationCreate
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
    assert completed.duration_ms is not None
    assert completed.retry_count == 0
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
    assert "larger in frame" in regenerated.revised_prompt
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
    assert completed.validation_result["violations"] == ["resolution"]
    assert completed.quality_check.resolution["status"] == "failed"
    assert completed.quality_check.product_similarity["status"] == "unavailable"
    assert completed.quality_check.text_risk["status"] == "unavailable"
    assert completed.quality_check.watermark_risk["status"] == "unavailable"
    assert completed.quality_check.review_required is True
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
    png = MockImageGenerationProvider().generate(
        ImageGenerationRequest(
            job_id="fixture",
            prompt="fixture",
            references=(),
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
            references=(
                ReferenceImage(
                    asset_version_id="source",
                    content=b"source",
                    filename="source.png",
                    mime_type="image/png",
                ),
            ),
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


def test_unimplemented_providers_report_unavailable_instead_of_faking_output():
    reference = ReferenceImage("source", b"image", "source.png", "image/png")
    generation_request = ImageGenerationRequest(
        job_id="job",
        prompt="strict",
        references=(reference,),
        size="1024x1024",
        width=1024,
        height=1024,
        quality="medium",
        output_format="png",
        timeout_seconds=10,
    )
    transform_request = ImageTransformationRequest(
        job_id="job", source=reference, timeout_seconds=10
    )
    calls = [
        lambda: ComfyUIImageGenerationProvider().generate(generation_request),
        lambda: RembgBackgroundRemovalProvider().remove_background(transform_request),
        lambda: RealESRGANUpscaleProvider().upscale(transform_request),
    ]
    for call in calls:
        with pytest.raises(ImageProviderError) as captured:
            call()
        assert captured.value.code == "provider_unavailable"


def test_generation_modes_default_by_asset_slot(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    _, source, plan = plan_context(session, storage)
    main = JobService(session, dispatcher).create_plan_jobs(
        VisualPlanGenerationCreate(
            plan_id=plan.id, source_version_id=source.id, slot_ids=[plan.slots[0].id]
        )
    )[0]
    assert main.generation_mode is GenerationMode.STRICT

    for slot, expected in [
        (ImageSlot.SCENE, GenerationMode.BALANCED),
        (ImageSlot.COMPARE, GenerationMode.CREATIVE),
    ]:
        RuleService(session).create_rule(
            PlatformRuleCreate(
                platform=PlatformCode.TEMU,
                market="US",
                category="kitchen",
                image_slot=slot,
                version="3.0.0",
                effective_date=date(2026, 8, 1),
            )
        )
        job = JobService(session, dispatcher).create_job(
            GenerationJobCreate(
                source_version_id=source.id,
                platform=PlatformCode.TEMU,
                market="US",
                category="kitchen",
                image_slot=slot,
            )
        )
        assert job.generation_mode is expected


class CaptureReferencesProvider(MockImageGenerationProvider):
    def __init__(self):
        self.references = ()

    def generate(self, request):
        self.references = request.references
        return super().generate(request)


def test_multiple_original_angles_are_recorded_and_sent_to_provider(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    product, source, plan = plan_context(session, storage)
    second = AssetService(session, storage).create_original(
        product.id, b"supplier-side", "mug-side.jpg", "image/jpeg", label="side angle"
    ).versions[0]
    job = JobService(session, dispatcher).create_plan_jobs(
        VisualPlanGenerationCreate(
            plan_id=plan.id,
            reference_asset_version_ids=[source.id, second.id],
            slot_ids=[plan.slots[0].id],
        )
    )[0]
    provider = CaptureReferencesProvider()

    GenerationWorker(session, storage, provider).process(job.id)

    assert job.reference_asset_version_ids == [str(source.id), str(second.id)]
    assert [item.asset_version_id for item in provider.references] == [
        str(source.id),
        str(second.id),
    ]
    assert len(job.parameters["task"]["references"]) == 2


class PassingSimilarityAnalyzer:
    name = "test-similarity"

    def analyze(self, output, references):
        return AnalyzerResult(status="passed", score=0.97)


def test_quality_analyzers_are_injectable(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    _, source, plan = plan_context(session, storage)
    job = JobService(session, dispatcher).create_plan_jobs(
        VisualPlanGenerationCreate(
            plan_id=plan.id, source_version_id=source.id, slot_ids=[plan.slots[0].id]
        )
    )[0]
    evaluator = GenerationQualityEvaluator(product_similarity=PassingSimilarityAnalyzer())

    completed = GenerationWorker(session, storage, quality_evaluator=evaluator).process(job.id)

    assert completed.quality_check.product_similarity == {"status": "passed", "score": 0.97}


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
    assert processed.json()["generation_mode"] == "STRICT"
    assert processed.json()["reference_asset_version_ids"] == [str(source.id)]
    assert processed.json()["quality_check"]["resolution"]["status"] == "passed"
    attempts = client.get(f"/api/v1/generation-jobs/{job['id']}/attempts")
    assert attempts.status_code == 200
    assert len(attempts.json()) == 1

    regenerated = client.post(
        f"/api/v1/generation-jobs/{job['id']}/regenerate",
        json={"feedback": "Use a tighter crop"},
    )
    assert regenerated.status_code == 200
    assert regenerated.json()["parent_job_id"] == job["id"]
