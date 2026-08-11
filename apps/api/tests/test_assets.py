from pathlib import Path

import pytest
from app.assets.models import AssetStatus, AssetType
from app.assets.service import AssetInvariantError, AssetService
from app.catalog.schemas import ProductCreate
from app.catalog.service import CatalogService

from tests.conftest import MemoryObjectStorage

REAL_CLOTH = (Path(__file__).parent / "fixtures" / "gray_cleaning_cloth_original.png").read_bytes()


def test_original_upload_creates_immutable_first_version(client):
    product = client.post(
        "/api/v1/products", json={"name": "Travel cup", "category": "kitchen"}
    ).json()
    response = client.post(
        f"/api/v1/products/{product['id']}/assets/original",
        files={"file": ("supplier.png", REAL_CLOTH, "image/png")},
        data={"label": "front view"},
    )

    assert response.status_code == 201
    asset = response.json()
    assert asset["asset_type"] == "ORIGINAL"
    assert len(asset["versions"]) == 1
    assert asset["versions"][0]["version_number"] == 1
    assert asset["versions"][0]["checksum_sha256"]
    assert asset["versions"][0]["width"] == 1254
    assert asset["versions"][0]["height"] == 1254
    assert asset["versions"][0]["mime_type"] == "image/png"


def test_processing_creates_new_asset_and_version(session):
    storage = MemoryObjectStorage()
    product = CatalogService(session).create_product(
        ProductCreate(name="Lamp", category="lighting")
    )
    assets = AssetService(session, storage)
    original = assets.create_original(product.id, b"raw", "raw.png", "image/png")
    source = original.versions[0]

    derived = assets.create_derived(
        source.id, AssetType.MAIN, b"processed", "main.webp", "image/webp"
    )

    assert derived.id != original.id
    assert derived.versions[0].source_version_id == source.id
    assert storage.get(source.object_key) == b"raw"
    assert storage.get(derived.versions[0].object_key) == b"processed"
    assert source.object_key != derived.versions[0].object_key


def test_original_chain_rejects_processed_versions(session):
    storage = MemoryObjectStorage()
    product = CatalogService(session).create_product(ProductCreate(name="Bag", category="fashion"))
    assets = AssetService(session, storage)
    original = assets.create_original(product.id, b"raw", "raw.png", "image/png")

    with pytest.raises(AssetInvariantError, match="ORIGINAL assets are immutable"):
        assets.append_processed_version(
            original.id, original.versions[0].id, b"overwrite", "new.png", "image/png"
        )


def test_derived_asset_and_version_crud_preserves_object_history(session):
    storage = MemoryObjectStorage()
    product = CatalogService(session).create_product(
        ProductCreate(name="Desk light", category="lighting")
    )
    assets = AssetService(session, storage)
    original = assets.create_original(product.id, b"raw", "raw.png", "image/png")
    derived = assets.create_derived(
        original.versions[0].id,
        AssetType.DETAIL,
        b"detail-v1",
        "detail.png",
        "image/png",
    )
    first = derived.versions[0]
    assert first.status is AssetStatus.REVIEW

    updated_asset = assets.update_asset(derived.id, label="Handle close-up")
    assert updated_asset.label == "Handle close-up"
    version = assets.append_processed_version(
        derived.id,
        first.id,
        b"detail-v2",
        "detail-v2.png",
        "image/png",
    )
    assert version.version_number == 2
    assert version.status is AssetStatus.DRAFT
    assert storage.get(first.object_key) == b"detail-v1"

    processing = assets.update_version_status(version.id, AssetStatus.PROCESSING)
    assert processing.status is AssetStatus.PROCESSING
    assert assets.update_version_status(version.id, AssetStatus.REVIEW).status is AssetStatus.REVIEW
    assets.delete_version(version.id)
    assert [item.id for item in assets.list_versions(derived.id)] == [first.id]
    assert version.object_key in storage.objects

    assets.archive_asset(derived.id)
    assert assets.list_product_assets(product.id) == [original]


def test_original_asset_and_version_crud_is_blocked(session):
    storage = MemoryObjectStorage()
    product = CatalogService(session).create_product(
        ProductCreate(name="Protected", category="demo")
    )
    assets = AssetService(session, storage)
    original = assets.create_original(product.id, b"raw", "raw.png", "image/png")

    with pytest.raises(AssetInvariantError, match="immutable"):
        assets.update_asset(original.id, label="changed")
    with pytest.raises(AssetInvariantError, match="cannot be deleted"):
        assets.archive_asset(original.id)
    with pytest.raises(AssetInvariantError, match="immutable"):
        assets.update_version_status(original.versions[0].id, AssetStatus.PROCESSING)
    with pytest.raises(AssetInvariantError, match="cannot be deleted"):
        assets.delete_version(original.versions[0].id)


def test_processed_version_rejects_cross_product_source(session):
    storage = MemoryObjectStorage()
    catalog = CatalogService(session)
    first = catalog.create_product(ProductCreate(name="First", category="demo"))
    second = catalog.create_product(ProductCreate(name="Second", category="demo"))
    assets = AssetService(session, storage)
    first_source = assets.create_original(first.id, b"first", "first.png", "image/png").versions[0]
    second_source = assets.create_original(
        second.id, b"second", "second.png", "image/png"
    ).versions[0]
    derived = assets.create_derived(
        first_source.id, AssetType.MAIN, b"main", "main.png", "image/png"
    )

    with pytest.raises(AssetInvariantError, match="same product"):
        assets.append_processed_version(
            derived.id,
            second_source.id,
            b"invalid",
            "invalid.png",
            "image/png",
        )


def test_asset_upload_rejects_non_image_content(client):
    product = client.post("/api/v1/products", json={"name": "Document", "category": "demo"}).json()

    response = client.post(
        f"/api/v1/products/{product['id']}/assets",
        files={"file": ("payload.txt", b"not-an-image", "text/plain")},
        data={"asset_type": "ORIGINAL"},
    )

    assert response.status_code == 415
