import io

import pytest
from app.assets.models import AssetStatus, AssetType, AssetVersion, ContentKind
from app.assets.service import AssetService
from app.catalog.schemas import Dimensions, ProductCreate, SKUCreate
from app.catalog.service import CatalogService
from app.jobs.models import JobStatus, ProviderType, TaskType
from app.templates.bindings import TemplateBindingError, TemplateBindingResolver, format_dimension
from app.templates.models import TemplateStatus, TemplateType
from app.templates.renderer import DeterministicTemplateRenderer
from app.templates.schema_types import validate_template_schema
from app.templates.schemas import TemplateCreate, TemplateRenderCreate, TemplateVersionInput
from app.templates.service import TemplateRenderService, TemplateService
from PIL import Image, ImageChops
from pydantic import ValidationError

from tests.conftest import MemoryObjectStorage


def schema(text="{{product.name}}"):
    return {
        "schemaVersion": "1.0",
        "layers": [
            {
                "id": "product",
                "type": "IMAGE",
                "x": 20,
                "y": 20,
                "width": 220,
                "height": 220,
                "assetSource": "{{asset.cutout}}",
                "fit": "contain",
                "zIndex": 1,
            },
            {
                "id": "title",
                "type": "TEXT",
                "x": 20,
                "y": 250,
                "width": 220,
                "height": 40,
                "text": text,
                "fontSize": 20,
                "zIndex": 2,
            },
        ],
    }


def create_template(session, code="TEST_MAIN_01"):
    return TemplateService(session).create(
        TemplateCreate(
            name="Test main",
            code=code,
            template_type=TemplateType.MAIN,
            status=TemplateStatus.DRAFT,
            canvas_width=300,
            canvas_height=300,
            background={"color": "#ffffff"},
            schema_json=schema(),
        )
    )


def png_bytes(color="#5b8f72"):
    output = io.BytesIO()
    Image.new("RGBA", (120, 160), color).save(output, format="PNG")
    return output.getvalue()


def test_contain_scales_up_to_layer_bounds_and_preserves_ratio(session):
    product, _, storage, _, approved = product_with_assets(session)
    template = create_template(session, "CONTAIN_SCALE_01")
    bindings = TemplateBindingResolver(session)
    rendered = DeterministicTemplateRenderer(storage, bindings).render(
        template.latest_version,
        bindings.product_snapshot(product, None),
        {"{{asset.cutout}}": approved},
        output_format="PNG",
        quality=92,
    )
    with Image.open(io.BytesIO(rendered.content)).convert("RGB") as image:
        background = Image.new("RGB", image.size, "white")
        layer_box = (20, 20, 240, 240)
        bbox = ImageChops.difference(
            image.crop(layer_box), background.crop(layer_box)
        ).getbbox()
    assert bbox == (28, 0, 193, 220)


def test_main_postprocessing_fill_ratio_and_fidelity_limits(session):
    product, _, storage, _, approved = product_with_assets(session)
    template = create_template(session, "MAIN_POSTPROCESS_01")
    bindings = TemplateBindingResolver(session)
    rendered = DeterministicTemplateRenderer(storage, bindings).render(
        template.latest_version,
        bindings.product_snapshot(product, None),
        {"{{asset.cutout}}": approved},
        output_format="PNG",
        quality=92,
        subject_fill_ratio=0.78,
        edge_cleanup=True,
        tone_correction=True,
    )
    assert rendered.metadata["subject_bbox"] == [62, 33, 238, 267]
    assert rendered.metadata["actual_subject_fill_ratio"] == 0.78
    assert rendered.metadata["warnings"] == ["SOURCE_QUALITY_LOW"]
    assert rendered.metadata["processors"]["edge_cleanup"]["alpha_preserved"] is True
    tone = rendered.metadata["processors"]["tone_correction"]
    assert tone["limits"]["max_channel_gain_delta"] == 0.025
    assert tone["brightness_factor"] <= 1.04
    assert tone["contrast_factor"] <= 1.03


def test_subject_fill_ratio_is_bounded():
    data = {
        "template_version_id": "20000000-0000-4000-8000-000000000001",
        "product_id": "10000000-0000-4000-8000-000000000001",
    }
    with pytest.raises(ValidationError):
        TemplateRenderCreate(**data, subject_fill_ratio=0.69)
    with pytest.raises(ValidationError):
        TemplateRenderCreate(**data, subject_fill_ratio=0.86)


def product_with_assets(session):
    catalog = CatalogService(session)
    product = catalog.create_product(
        ProductCreate(
            name="Travel kettle",
            category="kitchen",
            material="silicone",
            color="sage",
            dimensions=Dimensions(length=30, width=20, height=12, unit="cm"),
            weight_value=0.8,
            weight_unit="kg",
            selling_points=["Foldable", "Dual voltage"],
        )
    )
    sku = catalog.add_sku(product.id, SKUCreate(code="KETTLE-SAGE"))
    storage = MemoryObjectStorage()
    assets = AssetService(session, storage)
    original = assets.create_original(product.id, png_bytes(), "supplier.png", "image/png")
    cutout = assets.create_derived(
        original.versions[0].id,
        AssetType.CUTOUT,
        png_bytes(),
        "cutout.png",
        "image/png",
        width=120,
        height=160,
    )
    approved = assets.update_version_status(cutout.versions[0].id, AssetStatus.APPROVED)
    return product, sku, storage, assets, approved


def test_template_crud_and_copy_api(client):
    payload = {
        "name": "Minimal main",
        "code": "API_MAIN_01",
        "template_type": "MAIN",
        "canvas_width": 300,
        "canvas_height": 300,
        "background": {"color": "#ffffff"},
        "schema_json": schema(),
    }
    created = client.post("/api/v1/templates", json=payload)
    assert created.status_code == 201
    template = created.json()
    assert template["latest_version"]["version"] == 1
    assert (
        client.patch(f"/api/v1/templates/{template['id']}", json={"status": "ACTIVE"}).json()[
            "status"
        ]
        == "ACTIVE"
    )
    copied = client.post(
        f"/api/v1/templates/{template['id']}/copy",
        json={"code": "API_MAIN_COPY_01", "name": "Copy"},
    )
    assert copied.status_code == 201
    assert copied.json()["status"] == "DRAFT"
    assert client.delete(f"/api/v1/templates/{template['id']}").json()["status"] == "ARCHIVED"


def test_template_version_is_append_only(session):
    template = create_template(session)
    first_id = template.latest_version.id
    first_schema = template.latest_version.schema_json
    second = TemplateService(session).create_version(
        template.id,
        TemplateVersionInput(
            canvas_width=400,
            canvas_height=400,
            background={"color": "#f5f5f5"},
            schema_json=schema("{{product.material}}"),
        ),
    )
    assert second.version == 2
    assert TemplateService(session).get_version(template.id, first_id).schema_json == first_schema
    assert [item.version for item in TemplateService(session).list_versions(template.id)] == [2, 1]


def test_template_json_schema_rejects_invalid_layers():
    with pytest.raises(ValidationError, match="approved asset binding"):
        validate_template_schema(
            {
                "schemaVersion": "1.0",
                "layers": [{"id": "bad", "type": "IMAGE", "assetSource": "{{asset.original}}"}],
            }
        )
    with pytest.raises(ValidationError, match="unique"):
        validate_template_schema(
            {
                "schemaVersion": "1.0",
                "layers": [
                    {"id": "same", "type": "TEXT", "text": "A"},
                    {"id": "same", "type": "TEXT", "text": "B"},
                ],
            }
        )


def test_dynamic_binding_and_dimension_units(session):
    product, sku, _, _, _ = product_with_assets(session)
    resolver = TemplateBindingResolver(session)
    snapshot = resolver.product_snapshot(product, sku)
    assert (
        resolver.resolve_text("{{product.name}} / {{sku.code}}", snapshot)
        == "Travel kettle / KETTLE-SAGE"
    )
    assert snapshot["product"]["length"] == "30 cm"
    assert format_dimension(300, "mm", "cm") == "30 cm"
    assert format_dimension("2.54", "cm", "inch") == "1 inch"


def test_only_approved_assets_can_be_selected(session):
    product, _, storage, assets, approved = product_with_assets(session)
    rejected_asset = assets.create_derived(
        approved.id, AssetType.CUTOUT, png_bytes("#aa0000"), "rejected.png", "image/png"
    )
    rejected = assets.update_version_status(rejected_asset.versions[0].id, AssetStatus.REJECTED)
    resolver = TemplateBindingResolver(session)
    chosen = resolver.approved_assets(product.id, {"{{asset.cutout}}"})
    assert chosen["{{asset.cutout}}"].id == approved.id
    with pytest.raises(TemplateBindingError, match="APPROVED"):
        resolver.approved_assets(
            product.id,
            {"{{asset.cutout}}"},
            {"{{asset.cutout}}": rejected.id},
        )
    assert storage.get(approved.object_key) == png_bytes()


def test_smoke_test_approved_asset_is_not_used_for_production_template_binding(session):
    product, _, _, _, approved = product_with_assets(session)
    approved.status = AssetStatus.APPROVED_FOR_SMOKE_TEST
    session.commit()

    with pytest.raises(TemplateBindingError, match="APPROVED"):
        TemplateBindingResolver(session).approved_assets(
            product.id, {"{{asset.cutout}}"}
        )


def test_demo_asset_is_not_used_for_production_template_binding(session):
    product, _, _, assets, approved = product_with_assets(session)
    demo_asset = assets.create_derived(
        approved.id,
        AssetType.CUTOUT,
        png_bytes("#777777"),
        "demo.png",
        "image/png",
    )
    demo = assets.update_version_status(demo_asset.versions[0].id, AssetStatus.APPROVED)
    demo.contains_demo_data = True
    demo.demo_data_fields = ["product.material"]
    session.commit()
    resolver = TemplateBindingResolver(session)

    assert resolver.approved_assets(product.id, {"{{asset.cutout}}"})[
        "{{asset.cutout}}"
    ].id == approved.id
    with pytest.raises(TemplateBindingError, match="APPROVED"):
        resolver.approved_assets(
            product.id,
            {"{{asset.cutout}}"},
            {"{{asset.cutout}}": demo.id},
        )


def test_render_task_creates_review_version_and_traceability(session):
    product, sku, storage, _, approved = product_with_assets(session)
    template = create_template(session, "RENDER_MAIN_01")
    job, record = TemplateRenderService(session, storage).render(
        TemplateRenderCreate(
            template_version_id=template.latest_version.id,
            product_id=product.id,
            sku_id=sku.id,
        )
    )
    assert job.status is JobStatus.COMPLETED
    assert job.provider_type is ProviderType.TEMPLATE
    assert job.task_type is TaskType.RENDER_MAIN_TEMPLATE
    assert record.source_asset_version_ids == [str(approved.id)]
    assert record.product_data_snapshot["product"]["length"] == "30 cm"
    assert record.output_asset_version_id == job.output_version_id
    output = job.output_version_id and session.get(type(approved), job.output_version_id)
    assert output is not None
    assert output.status is AssetStatus.REVIEW
    assert output.source_version_id == approved.id
    assert storage.get(approved.object_key) == png_bytes()
    assert storage.get(output.object_key) != storage.get(approved.object_key)


def test_detail_templates_record_content_kind_and_demo_data_fields(session):
    product, sku, storage, _, _ = product_with_assets(session)
    product.material = "DEMO_TEST_DATA"
    product.dimensions = {
        "length": 30,
        "width": 30,
        "unit": "cm",
        "data_source": "DEMO_TEST_DATA",
    }
    product.selling_points = ["Soft texture", "Reusable", "Multi-purpose cleaning"]
    sku.attributes = {
        "data_source": "DEMO_TEST_DATA",
        "selling_point_description_1": "Demo layout copy only",
        "selling_point_description_2": "Demo layout copy only",
        "selling_point_description_3": "Demo layout copy only",
    }
    session.commit()
    templates = {item.code: item for item in TemplateService(session).list()}

    expectations = {
        "SELLING_POINT_01": (
            ContentKind.SELLING_POINT,
            {
                "product.name",
                "selling_point_1",
                "selling_point_2",
                "selling_point_3",
                "sku.selling_point_description_1",
                "sku.selling_point_description_2",
                "sku.selling_point_description_3",
            },
        ),
        "PARAMETER_01": (
            ContentKind.PARAMETER,
            {
                "product.name",
                "product.material",
                "product.color",
                "product.length",
                "product.width",
                "sku.code",
            },
        ),
    }
    for code, (content_kind, expected_fields) in expectations.items():
        job, record = TemplateRenderService(session, storage).render(
            TemplateRenderCreate(
                template_version_id=templates[code].latest_version.id,
                product_id=product.id,
                sku_id=sku.id,
            )
        )
        output = session.get(AssetVersion, job.output_version_id)
        assert output is not None
        assert output.asset.asset_type is AssetType.DETAIL
        assert output.asset.content_kind is content_kind
        assert output.status is AssetStatus.REVIEW
        assert output.contains_demo_data is True
        assert set(output.demo_data_fields) == expected_fields
        assert record.product_data_snapshot["data_source"] == "DEMO_TEST_DATA"
        assert record.product_data_snapshot["contains_demo_data"] is True
        assert job.output_metadata["content_kind"] == content_kind.value
        assert job.output_metadata["contains_demo_data"] is True


def test_content_demo_templates_use_optimized_layout_without_embedded_demo_copy(session):
    templates = {item.code: item for item in TemplateService(session).list()}
    selling = templates["SELLING_POINT_01"].latest_version
    parameter = templates["PARAMETER_01"].latest_version
    assert selling is not None and parameter is not None

    selling_layers = {layer["id"]: layer for layer in selling.schema_json["layers"]}
    product_width_ratio = selling_layers["product"]["width"] / selling.canvas_width
    assert 0.48 <= product_width_ratio <= 0.55
    assert [selling_layers[f"number-{index}"]["text"] for index in range(1, 4)] == [
        "01",
        "02",
        "03",
    ]
    assert [
        selling_layers[f"point-{index}-title"]["text"] for index in range(1, 4)
    ] == [f"{{{{selling_point_{index}}}}}" for index in range(1, 4)]
    assert [
        selling_layers[f"point-{index}-description"]["text"]
        for index in range(1, 4)
    ] == [f"{{{{sku.selling_point_description_{index}}}}}" for index in range(1, 4)]

    parameter_layers = {layer["id"]: layer for layer in parameter.schema_json["layers"]}
    assert parameter_layers["panel"]["width"] < 650
    assert parameter_layers["product"]["width"] > 700
    assert parameter_layers["material"]["text"] == "{{product.material}}"
    assert parameter_layers["color"]["text"] == "{{product.color}}"
    assert parameter_layers["size"]["text"] == "{{product.length}} ×\n{{product.width}}"
    assert parameter_layers["sku"]["text"] == "{{sku.code}}"
    assert "DEMO_TEST_DATA" not in str(parameter.schema_json)
