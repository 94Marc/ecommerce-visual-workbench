def test_product_and_sku_flow(client):
    created = client.post(
        "/api/v1/products",
        json={
            "name": "Foldable travel kettle",
            "category": "home_appliances",
            "material": "food-grade silicone",
            "color": "sage",
            "dimensions": {"length": 18, "width": 13, "height": 10, "unit": "cm"},
            "weight_value": 0.72,
            "weight_unit": "kg",
            "selling_points": ["Dual voltage", "Collapses for packing"],
        },
    )
    assert created.status_code == 201
    product = created.json()
    assert product["name"] == "Foldable travel kettle"
    assert product["skus"] == []

    sku = client.post(
        f"/api/v1/products/{product['id']}/skus",
        json={"code": "KETTLE-SAGE-01", "attributes": {"plug": "EU"}},
    )
    assert sku.status_code == 201
    assert sku.json()["attributes"] == {"plug": "EU"}

    fetched = client.get(f"/api/v1/products/{product['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["skus"][0]["code"] == "KETTLE-SAGE-01"


def test_sku_code_is_unique(client):
    first = client.post(
        "/api/v1/products", json={"name": "A", "category": "demo"}
    ).json()
    second = client.post(
        "/api/v1/products", json={"name": "B", "category": "demo"}
    ).json()
    payload = {"code": "SHARED", "attributes": {}}

    assert client.post(f"/api/v1/products/{first['id']}/skus", json=payload).status_code == 201
    duplicate = client.post(f"/api/v1/products/{second['id']}/skus", json=payload)
    assert duplicate.status_code == 409


def test_weight_requires_unit(client):
    response = client.post(
        "/api/v1/products",
        json={"name": "Incomplete", "category": "demo", "weight_value": 1.2},
    )
    assert response.status_code == 422

