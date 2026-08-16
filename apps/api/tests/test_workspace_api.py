from datetime import date
from pathlib import Path

from app.rules.models import ImageSlot, PlatformCode
from app.rules.schemas import PlatformRuleCreate
from app.rules.service import RuleService

REAL_CLOTH = (Path(__file__).parent / "fixtures" / "gray_cleaning_cloth_original.png").read_bytes()


def create_product_and_original(client):
    product = client.post(
        "/api/v1/products",
        json={"name": "Visual workspace item", "category": "home"},
    ).json()
    original = client.post(
        f"/api/v1/products/{product['id']}/assets/original",
        files={"file": ("supplier.png", REAL_CLOTH, "image/png")},
    ).json()
    return product, original


def test_asset_and_version_crud_api(client):
    product, original = create_product_and_original(client)
    source_id = original["versions"][0]["id"]

    derived_response = client.post(
        f"/api/v1/products/{product['id']}/assets",
        data={
            "asset_type": "DETAIL",
            "content_kind": "FEATURE",
            "source_version_id": source_id,
            "label": "Detail crop",
        },
        files={"file": ("detail.png", REAL_CLOTH, "image/png")},
    )
    assert derived_response.status_code == 201
    derived = derived_response.json()
    assert derived["content_kind"] == "FEATURE"
    version_id = derived["versions"][0]["id"]
    assert derived["versions"][0]["status"] == "REVIEW"
    assert derived["versions"][0]["contains_demo_data"] is False
    assert derived["versions"][0]["demo_data_fields"] == []

    updated = client.patch(f"/api/v1/assets/{derived['id']}", json={"label": "Handle detail"})
    assert updated.status_code == 200
    assert updated.json()["label"] == "Handle detail"

    next_version = client.post(
        f"/api/v1/assets/{derived['id']}/versions",
        data={"source_version_id": version_id},
        files={"file": ("detail-v2.png", REAL_CLOTH, "image/png")},
    )
    assert next_version.status_code == 201
    assert next_version.json()["version_number"] == 2
    assert next_version.json()["status"] == "DRAFT"

    processing = client.patch(
        f"/api/v1/asset-versions/{next_version.json()['id']}",
        json={"status": "PROCESSING"},
    )
    assert processing.status_code == 200
    assert processing.json()["status"] == "PROCESSING"

    content = client.get(f"/api/v1/asset-versions/{version_id}/content")
    assert content.status_code == 200
    assert content.content == REAL_CLOTH

    assert client.delete(f"/api/v1/assets/{original['id']}").status_code == 409
    assert client.delete(f"/api/v1/assets/{derived['id']}").status_code == 204


def test_review_crud_api_and_status_sync(client, session):
    product, original = create_product_and_original(client)
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
    created_job = client.post(
        "/api/v1/generation-jobs",
        json={
            "source_version_id": original["versions"][0]["id"],
            "platform": "temu",
            "market": "US",
            "category": "home",
            "image_slot": "MAIN",
            "parameters": {},
        },
    )
    assert created_job.status_code == 201
    completed = client.post(f"/api/v1/generation-jobs/{created_job.json()['id']}/simulate")
    assert completed.status_code == 200
    version_id = completed.json()["output_version_id"]

    review = client.post(
        f"/api/v1/asset-versions/{version_id}/reviews",
        json={"decision": "approved", "reviewer": "API reviewer", "comment": "Ready"},
    )
    assert review.status_code == 201
    review_id = review.json()["review"]["id"]
    assert client.get(f"/api/v1/asset-versions/{version_id}").json()["status"] == "APPROVED"

    fetched = client.get(f"/api/v1/asset-versions/{version_id}/reviews/{review_id}")
    assert fetched.status_code == 200
    edited = client.patch(
        f"/api/v1/asset-versions/{version_id}/reviews/{review_id}",
        json={"comment": "Approved after final inspection"},
    )
    assert edited.status_code == 200
    assert edited.json()["comment"] == "Approved after final inspection"

    assert (
        client.delete(f"/api/v1/asset-versions/{version_id}/reviews/{review_id}").status_code == 204
    )
    assert client.get(f"/api/v1/asset-versions/{version_id}").json()["status"] == "REVIEW"
