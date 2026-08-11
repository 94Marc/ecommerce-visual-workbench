import copy
import hashlib
import io
import json
import uuid
import zipfile
from datetime import date
from pathlib import Path

import pytest
from app.assets.models import AssetStatus, AssetType, AssetVersion
from app.assets.service import AssetService
from app.assets.storage import get_object_storage
from app.core.config import Settings
from app.exports.schemas import ExportCreate
from app.exports.service import ExportService
from app.jobs.models import JobStatus, ValidationStatus
from app.jobs.providers import (
    ComfyUIImageGenerationProvider,
    ImageGenerationRequest,
    ImageTransformationRequest,
    ProviderUnavailableError,
    RealESRGANUpscaleProvider,
    ReferenceImage,
    RembgBackgroundRemovalProvider,
)
from app.plans.schemas import AssetSlotInput, ProductVisualPlanCreate
from app.plans.service import VisualPlanService
from app.rules.models import ImageSlot, PlatformCode
from app.rules.schemas import PlatformRuleCreate
from app.rules.service import RuleService
from app.templates.bindings import TemplateBindingError
from app.templates.schemas import TemplateRenderCreate, TemplateVersionInput
from app.templates.service import TemplateRenderService, TemplateService

from tests.conftest import MemoryObjectStorage

FIXTURE = Path(__file__).parent / "fixtures" / "gray_cleaning_cloth_original.png"
ORIGINAL_BYTES = FIXTURE.read_bytes()
ORIGINAL_SHA256 = "813d14ad50adeca43fa818c91fe9691825b5364a0340af35e23d9e62f816f7bc"
SKU_CODE = "TEST-CLOTH-001"


def _assert_real_providers_are_unavailable(source_id) -> None:
    reference = ReferenceImage(
        asset_version_id=str(source_id),
        content=ORIGINAL_BYTES,
        filename=FIXTURE.name,
        mime_type="image/png",
    )
    transformation = ImageTransformationRequest(
        job_id="phase-6-provider-preflight",
        source=reference,
        timeout_seconds=1,
    )
    generation = ImageGenerationRequest(
        job_id="phase-6-provider-preflight",
        prompt="Place the supplied cleaning cloth in a realistic cleaning scene.",
        references=(reference,),
        size="1254x1254",
        width=1254,
        height=1254,
        quality="medium",
        output_format="png",
        timeout_seconds=1,
        workflow_id="product_usage",
        workflow_file="product_usage.json",
        generation_mode="BALANCED",
    )
    calls = (
        lambda: RembgBackgroundRemovalProvider(Settings(rembg_enabled=False)).remove_background(
            transformation
        ),
        lambda: RealESRGANUpscaleProvider(Settings(realesrgan_enabled=False)).upscale(
            transformation
        ),
        lambda: ComfyUIImageGenerationProvider(Settings(comfyui_enabled=False)).generate(
            generation
        ),
    )
    for call in calls:
        with pytest.raises(ProviderUnavailableError) as captured:
            call()
        assert captured.value.code == "provider_unavailable"


def _flat_cloth_template_versions(templates: TemplateService):
    by_code = {template.code: template for template in templates.list()}

    dimension = by_code["DIMENSION_BASIC_01"]
    dimension_schema = copy.deepcopy(dimension.latest_version.schema_json)
    height_label = next(
        layer for layer in dimension_schema["layers"] if layer["id"] == "height-text"
    )
    height_label["text"] = "{{product.length}}"
    dimension_version = templates.create_version(
        dimension.id,
        TemplateVersionInput(
            canvas_width=dimension.latest_version.canvas_width,
            canvas_height=dimension.latest_version.canvas_height,
            background=dimension.latest_version.background,
            schema_json=dimension_schema,
        ),
    )

    parameter = by_code["PARAMETER_01"]
    parameter_schema = copy.deepcopy(parameter.latest_version.schema_json)
    parameter_schema["layers"] = [
        layer
        for layer in parameter_schema["layers"]
        if layer["id"] not in {"material", "weight"}
    ]
    size_label = next(layer for layer in parameter_schema["layers"] if layer["id"] == "size")
    size_label["text"] = "Size  {{product.length}} × {{product.width}}"
    parameter_version = templates.create_version(
        parameter.id,
        TemplateVersionInput(
            canvas_width=parameter.latest_version.canvas_width,
            canvas_height=parameter.latest_version.canvas_height,
            background=parameter.latest_version.background,
            schema_json=parameter_schema,
        ),
    )

    return by_code, {
        "MAIN_WHITE_01": by_code["MAIN_WHITE_01"].latest_version,
        "DIMENSION_BASIC_01": dimension_version,
        "SELLING_POINT_01": by_code["SELLING_POINT_01"].latest_version,
        "PARAMETER_01": parameter_version,
        "DETAIL_CLOSEUP_01": by_code["DETAIL_CLOSEUP_01"].latest_version,
    }


def _create_rules(session):
    rules = RuleService(session)
    common = {
        "platform": PlatformCode.TEMU,
        "market": "US",
        "category": "cleaning-cloth",
        "version": "1.0.0",
        "effective_date": date(2026, 1, 1),
        "min_width": 1500,
        "min_height": 1500,
        "ratio": "1:1",
        "max_size": 10 * 1024 * 1024,
        "watermark_allowed": False,
        "extra_constraints": {"formats": ["image/png"]},
    }
    return {
        ImageSlot.MAIN: rules.create_rule(
            PlatformRuleCreate(
                **common,
                image_slot=ImageSlot.MAIN,
                text_allowed=False,
            )
        ),
        ImageSlot.DETAIL: rules.create_rule(
            PlatformRuleCreate(
                **common,
                image_slot=ImageSlot.DETAIL,
                text_allowed=True,
            )
        ),
        ImageSlot.DIMENSION: rules.create_rule(
            PlatformRuleCreate(
                **common,
                image_slot=ImageSlot.DIMENSION,
                text_allowed=True,
            )
        ),
    }


def test_real_cleaning_cloth_end_to_end_validation(client, session):
    storage: MemoryObjectStorage = client.app.dependency_overrides[get_object_storage]()
    product_response = client.post(
        "/api/v1/products",
        json={
            "name": "Gray Cleaning Cloth",
            "category": "cleaning-cloth",
            "color": "Gray",
            "dimensions": {"length": 30, "width": 30, "unit": "cm"},
            "selling_points": [
                "DEMO: 30 cm × 30 cm size display",
                "DEMO: cleaning-cloth visual workflow validation",
            ],
        },
    )
    assert product_response.status_code == 201
    product = product_response.json()
    assert product["material"] is None
    sku_response = client.post(
        f"/api/v1/products/{product['id']}/skus",
        json={
            "code": SKU_CODE,
            "attributes": {
                "chinese_note": "灰色清洁布",
                "declared_size": "30 cm × 30 cm",
            },
        },
    )
    assert sku_response.status_code == 201
    sku = sku_response.json()

    upload = client.post(
        f"/api/v1/products/{product['id']}/assets/original",
        data={"sku_id": sku["id"], "label": "Phase 6 real supplier ORIGINAL"},
        files={"file": (FIXTURE.name, ORIGINAL_BYTES, "image/jpeg")},
    )
    assert upload.status_code == 201
    original_asset = upload.json()
    original = original_asset["versions"][0]
    assert original["checksum_sha256"] == ORIGINAL_SHA256
    assert original["width"] == original["height"] == 1254
    assert original["mime_type"] == "image/png"
    assert original["byte_size"] == 2_454_772
    assert original["created_at"]
    original_bytes_before = storage.get(original["object_key"])

    original_update = client.patch(
        f"/api/v1/assets/{original_asset['id']}", json={"label": "changed"}
    )
    assert original_update.status_code == 409
    assert client.patch(
        f"/api/v1/asset-versions/{original['id']}", json={"status": "REVIEW"}
    ).status_code == 409
    assert client.post(
        f"/api/v1/assets/{original_asset['id']}/versions",
        data={"source_version_id": original["id"]},
        files={"file": (FIXTURE.name, ORIGINAL_BYTES, "image/png")},
    ).status_code == 409
    assert client.delete(f"/api/v1/assets/{original_asset['id']}").status_code == 409

    _assert_real_providers_are_unavailable(original["id"])

    assets = AssetService(session, storage)
    original_version_id = uuid.UUID(original["id"])
    source_copy = assets.create_derived(
        source_version_id=original_version_id,
        asset_type=AssetType.CUTOUT,
        content=ORIGINAL_BYTES,
        filename="e2e-real-source-prerequisite.png",
        mime_type="image/png",
        width=1254,
        height=1254,
        label="E2E prerequisite copied from ORIGINAL; NOT a rembg output",
    )
    approved_source = assets.update_version_status(
        source_copy.versions[0].id, AssetStatus.APPROVED
    )
    assert approved_source.source_version_id == original_version_id
    assert approved_source.checksum_sha256 == ORIGINAL_SHA256

    templates = TemplateService(session)
    by_code, versions = _flat_cloth_template_versions(templates)
    rules = _create_rules(session)
    platform = next(
        item for item in RuleService(session).list_platforms() if item.code == PlatformCode.TEMU
    )
    slots = [
        AssetSlotInput(
            code="MAIN_01",
            image_type=ImageSlot.MAIN,
            template_id=by_code["MAIN_WHITE_01"].id,
        ),
        AssetSlotInput(
            code="DETAIL_SELLING_POINT_01",
            image_type=ImageSlot.DETAIL,
            template_id=by_code["SELLING_POINT_01"].id,
        ),
        AssetSlotInput(
            code="DETAIL_PARAMETER_01",
            image_type=ImageSlot.DETAIL,
            template_id=by_code["PARAMETER_01"].id,
        ),
        AssetSlotInput(
            code="DETAIL_CLOSEUP_01",
            image_type=ImageSlot.DETAIL,
            template_id=by_code["DETAIL_CLOSEUP_01"].id,
        ),
        AssetSlotInput(
            code="DIMENSION_FRONT",
            image_type=ImageSlot.DIMENSION,
            template_id=by_code["DIMENSION_BASIC_01"].id,
        ),
        AssetSlotInput(code="SCENE_01", image_type=ImageSlot.SCENE),
        AssetSlotInput(code="USAGE_HOME", image_type=ImageSlot.USAGE),
        AssetSlotInput(
            code="PACKAGE_01",
            image_type=ImageSlot.PACKAGE,
            template_id=by_code["PACKAGE_01"].id,
        ),
    ]
    plan = VisualPlanService(session).create(
        ProductVisualPlanCreate(
            product_id=product["id"],
            platform_id=platform.id,
            rule_version_id=rules[ImageSlot.MAIN].id,
            name="Temu Phase 6 real-product validation",
            market="US",
            category="cleaning-cloth",
            requested_outputs={
                ImageSlot.MAIN: 1,
                ImageSlot.DETAIL: 3,
                ImageSlot.DIMENSION: 1,
                ImageSlot.SCENE: 1,
                ImageSlot.USAGE: 1,
                ImageSlot.PACKAGE: 1,
            },
            slots=slots,
        )
    )
    slots_by_code = {slot.code: slot for slot in plan.slots}

    render_cases = (
        ("MAIN_01", "MAIN_WHITE_01"),
        ("DETAIL_SELLING_POINT_01", "SELLING_POINT_01"),
        ("DETAIL_PARAMETER_01", "PARAMETER_01"),
        ("DETAIL_CLOSEUP_01", "DETAIL_CLOSEUP_01"),
        ("DIMENSION_FRONT", "DIMENSION_BASIC_01"),
    )
    rendered = []
    for slot_code, template_code in render_cases:
        job, record = TemplateRenderService(session, storage).render(
            TemplateRenderCreate(
                template_version_id=versions[template_code].id,
                product_id=product["id"],
                sku_id=sku["id"],
                asset_slot_id=slots_by_code[slot_code].id,
            )
        )
        output = session.get(AssetVersion, job.output_version_id)
        assert job.status is JobStatus.COMPLETED
        assert job.validation_status is ValidationStatus.PASSED
        assert output.status is AssetStatus.REVIEW
        assert output.source_version_id == approved_source.id
        assert record.source_asset_version_ids == [str(approved_source.id)]
        assert record.product_data_snapshot["product"]["material"] == ""
        assert record.product_data_snapshot["product"]["length"] == "30 cm"
        assert record.product_data_snapshot["product"]["width"] == "30 cm"
        review = client.post(
            f"/api/v1/asset-versions/{output.id}/reviews",
            json={
                "decision": "approved",
                "reviewer": "Phase 6 automated workflow acceptance",
                "comment": (
                    "Automated state-transition fixture after deterministic rule assertions; "
                    "not a human visual verdict."
                ),
            },
        )
        assert review.status_code == 201
        assert review.json()["review"]["decision"] == "approved"
        assert session.get(AssetVersion, output.id).status is AssetStatus.APPROVED
        rendered.append((job, output, record))

    with pytest.raises(TemplateBindingError, match="asset.package"):
        TemplateRenderService(session, storage).render(
            TemplateRenderCreate(
                template_version_id=by_code["PACKAGE_01"].latest_version.id,
                product_id=product["id"],
                sku_id=sku["id"],
                asset_slot_id=slots_by_code["PACKAGE_01"].id,
            )
        )

    bundle = ExportService(session, storage).create_bundle(
        ExportCreate(
            product_id=product["id"],
            platform=PlatformCode.TEMU,
            market="US",
            category="cleaning-cloth",
        )
    )
    with zipfile.ZipFile(io.BytesIO(storage.get(bundle.object_key))) as archive:
        names = set(archive.namelist())
        for directory in ("main", "detail", "dimension", "scene", "usage", "package"):
            assert f"{SKU_CODE}/{directory}/" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema_version"] == "2.0"
        assert manifest["product"]["name"] == "Gray Cleaning Cloth"
        assert manifest["sku"]["code"] == SKU_CODE
        assert manifest["platform"] == "temu"
        assert len(manifest["files"]) == len(rendered) == 5
        for item in manifest["files"]:
            assert item["filename"] in names
            assert item["asset_id"]
            assert item["asset_version_id"]
            assert item["asset_type"] in {"MAIN", "DETAIL", "DIMENSION"}
            assert item["asset_slot_id"]
            assert item["visual_plan_id"] == str(plan.id)
            assert item["template_provider"]["type"] == "TEMPLATE"
            assert item["template_provider"]["provider"] == "template"
            assert item["review_status"] == "APPROVED"
            assert item["rule_result"]["status"] == "passed"
            assert item["rule_result"]["validation"]["valid"] is True
            assert len(item["checksum_sha256"]) == 64

        missing = {item["slot"]: item["reason"] for item in manifest["missing_slots"]}
        assert missing == {
            "SCENE_01": "RULE_NOT_CONFIGURED",
            "USAGE_HOME": "RULE_NOT_CONFIGURED",
            "PACKAGE_01": "MISSING_SOURCE",
        }

    assert hashlib.sha256(storage.get(original["object_key"])).hexdigest() == ORIGINAL_SHA256
    assert storage.get(original["object_key"]) == original_bytes_before == ORIGINAL_BYTES
    assert len(assets.list_versions(uuid.UUID(original_asset["id"]))) == 1
