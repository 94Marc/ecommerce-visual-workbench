from datetime import date

from app.catalog.schemas import ProductCreate
from app.catalog.service import CatalogService
from app.plans.schemas import AssetSlotInput, ProductVisualPlanCreate, ProductVisualPlanUpdate
from app.plans.service import VisualPlanService
from app.rules.models import ImageSlot, PlatformCode
from app.rules.schemas import PlatformRuleCreate
from app.rules.service import RuleService
from app.templates.models import TemplateStatus, TemplateType
from app.templates.schemas import TemplateCreate
from app.templates.service import TemplateService


def context(session):
    product = CatalogService(session).create_product(
        ProductCreate(name="Travel kettle", category="kitchen")
    )
    rule = RuleService(session).create_rule(
        PlatformRuleCreate(
            platform=PlatformCode.TEMU,
            market="US",
            category="kitchen",
            image_slot=ImageSlot.MAIN,
            version="2.1.0",
            effective_date=date(2026, 8, 1),
            min_width=1600,
            min_height=1600,
            ratio="1:1",
            max_size=5242880,
            text_allowed=False,
        )
    )
    return product, RuleService(session).list_platforms()[0], rule


def make_plan(session, slots=None):
    product, platform, rule = context(session)
    return VisualPlanService(session).create(
        ProductVisualPlanCreate(
            product_id=product.id,
            platform_id=platform.id,
            rule_version_id=rule.id,
            name="Temu US launch",
            market="US",
            category="kitchen",
            requested_outputs={ImageSlot.MAIN: 2, ImageSlot.DETAIL: 1, ImageSlot.DIMENSION: 1},
            slots=slots,
        )
    )


def test_visual_plan_expands_quantities_to_deterministic_slots(session):
    assert [slot.code for slot in make_plan(session).slots] == [
        "MAIN_01",
        "MAIN_02",
        "DETAIL_01",
        "DIMENSION_01",
    ]


def test_visual_plan_supports_semantic_asset_slots(session):
    slots = [
        AssetSlotInput(code="MAIN_01", image_type=ImageSlot.MAIN),
        AssetSlotInput(code="MAIN_02", image_type=ImageSlot.MAIN),
        AssetSlotInput(code="DETAIL_FEATURE_01", image_type=ImageSlot.DETAIL),
        AssetSlotInput(code="DIMENSION_FRONT", image_type=ImageSlot.DIMENSION),
    ]
    assert [slot.code for slot in make_plan(session, slots).slots][-2:] == [
        "DETAIL_FEATURE_01",
        "DIMENSION_FRONT",
    ]


def test_visual_plan_update_rebuilds_slots(session):
    plan = make_plan(session)
    updated = VisualPlanService(session).update(
        plan.id, ProductVisualPlanUpdate(name="Approved", requested_outputs={ImageSlot.MAIN: 1})
    )
    assert updated.name == "Approved"
    assert [slot.code for slot in updated.slots] == ["MAIN_01"]


def test_visual_plan_slot_can_bind_a_template(session):
    template = TemplateService(session).create(
        TemplateCreate(
            name="White main",
            code="PLAN_MAIN_01",
            template_type=TemplateType.MAIN,
            status=TemplateStatus.ACTIVE,
            canvas_width=1600,
            canvas_height=1600,
            background={"color": "#ffffff"},
            schema_json={
                "schemaVersion": "1.0",
                "layers": [
                    {
                        "id": "product",
                        "type": "IMAGE",
                        "assetSource": "{{asset.cutout}}",
                        "width": 1200,
                        "height": 1200,
                    }
                ],
            },
        )
    )
    slots = [
        AssetSlotInput(code="MAIN_01", image_type=ImageSlot.MAIN, template_id=template.id),
        AssetSlotInput(code="MAIN_02", image_type=ImageSlot.MAIN),
        AssetSlotInput(code="DETAIL_FEATURE_01", image_type=ImageSlot.DETAIL),
        AssetSlotInput(code="DIMENSION_FRONT", image_type=ImageSlot.DIMENSION),
    ]
    plan = make_plan(session, slots)
    assert plan.slots[0].template_id == template.id


def test_visual_plan_api_crud(client, session):
    product, platform, rule = context(session)
    response = client.post(
        "/api/v1/visual-plans",
        json={
            "product_id": str(product.id),
            "platform_id": str(platform.id),
            "rule_version_id": str(rule.id),
            "name": "API plan",
            "market": "US",
            "category": "kitchen",
            "requested_outputs": {"MAIN": 2},
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert [slot["code"] for slot in payload["slots"]] == ["MAIN_01", "MAIN_02"]
    assert (
        client.get(f"/api/v1/visual-plans?product_id={product.id}").json()[0]["id"] == payload["id"]
    )
    assert client.delete(f"/api/v1/visual-plans/{payload['id']}").status_code == 204
