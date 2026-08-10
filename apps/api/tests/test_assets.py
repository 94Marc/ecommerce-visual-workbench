import pytest
from app.assets.models import AssetType
from app.assets.service import AssetInvariantError, AssetService
from app.catalog.schemas import ProductCreate
from app.catalog.service import CatalogService

from tests.conftest import MemoryObjectStorage


def test_original_upload_creates_immutable_first_version(client):
    product = client.post(
        "/api/v1/products", json={"name": "Travel cup", "category": "kitchen"}
    ).json()
    response = client.post(
        f"/api/v1/products/{product['id']}/assets/original",
        files={"file": ("supplier.jpg", b"supplier-original", "image/jpeg")},
        data={"label": "front view"},
    )

    assert response.status_code == 201
    asset = response.json()
    assert asset["asset_type"] == "ORIGINAL"
    assert len(asset["versions"]) == 1
    assert asset["versions"][0]["version_number"] == 1
    assert asset["versions"][0]["checksum_sha256"]


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
    product = CatalogService(session).create_product(
        ProductCreate(name="Bag", category="fashion")
    )
    assets = AssetService(session, storage)
    original = assets.create_original(product.id, b"raw", "raw.png", "image/png")

    with pytest.raises(AssetInvariantError, match="ORIGINAL assets are immutable"):
        assets.append_processed_version(
            original.id, original.versions[0].id, b"overwrite", "new.png", "image/png"
        )
