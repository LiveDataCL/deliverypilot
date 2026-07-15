import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.enums import UserRole
from tests.conftest import create_user_in_business, register_business

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _whoami(client: AsyncClient, access_token: str) -> dict:
    response = await client.get("/api/v1/auth/me", headers=_auth(access_token))
    assert response.status_code == 200
    return response.json()


async def test_create_and_list_products(client: AsyncClient):
    tokens = await register_business(client, business_name="Catalogo A", email="catalogoA@example.com")
    create_response = await client.post(
        "/api/v1/products",
        json={"name": "Bidon 20L retornable", "price": 3000, "unit": "bidon"},
        headers=_auth(tokens["access_token"]),
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["name"] == "Bidon 20L retornable"
    assert created["active"] is True
    assert created["is_combo"] is False

    list_response = await client.get("/api/v1/products", headers=_auth(tokens["access_token"]))
    assert list_response.status_code == 200
    body = list_response.json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["id"]


async def test_get_product_not_found_returns_404(client: AsyncClient):
    tokens = await register_business(client, business_name="Catalogo B", email="catalogoB@example.com")
    response = await client.get("/api/v1/products/999999", headers=_auth(tokens["access_token"]))
    assert response.status_code == 404
    assert response.json()["code"] == "product_not_found"


async def test_deactivating_a_product_does_not_delete_it(client: AsyncClient):
    tokens = await register_business(client, business_name="Catalogo C", email="catalogoC@example.com")
    created = (
        await client.post(
            "/api/v1/products",
            json={"name": "Bomba manual", "price": 5000, "unit": "unidad"},
            headers=_auth(tokens["access_token"]),
        )
    ).json()

    patch_response = await client.patch(
        f"/api/v1/products/{created['id']}",
        json={"active": False},
        headers=_auth(tokens["access_token"]),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["active"] is False

    get_response = await client.get(
        f"/api/v1/products/{created['id']}", headers=_auth(tokens["access_token"])
    )
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Bomba manual"


async def test_products_are_tenant_isolated(client: AsyncClient):
    tokens_a = await register_business(client, business_name="Catalogo D", email="catalogoD@example.com")
    tokens_b = await register_business(client, business_name="Catalogo E", email="catalogoE@example.com")

    product_b = (
        await client.post(
            "/api/v1/products",
            json={"name": "Producto de B", "price": 1000, "unit": "unidad"},
            headers=_auth(tokens_b["access_token"]),
        )
    ).json()

    get_response = await client.get(
        f"/api/v1/products/{product_b['id']}", headers=_auth(tokens_a["access_token"])
    )
    assert get_response.status_code == 404

    patch_response = await client.patch(
        f"/api/v1/products/{product_b['id']}",
        json={"active": False},
        headers=_auth(tokens_a["access_token"]),
    )
    assert patch_response.status_code == 404


async def test_combo_items_full_replace_flow(client: AsyncClient):
    tokens = await register_business(client, business_name="Catalogo Combo", email="combo1@example.com")
    headers = _auth(tokens["access_token"])

    bidon = (
        await client.post(
            "/api/v1/products",
            json={"name": "Bidon 20L", "price": 3000, "unit": "bidon"},
            headers=headers,
        )
    ).json()
    pack = (
        await client.post(
            "/api/v1/products",
            json={"name": "Pack botellas", "price": 2500, "unit": "pack"},
            headers=headers,
        )
    ).json()
    combo = (
        await client.post(
            "/api/v1/products",
            json={"name": "Combo Hogar", "price": 8500, "unit": "combo", "is_combo": True},
            headers=headers,
        )
    ).json()

    replace_response = await client.put(
        f"/api/v1/products/{combo['id']}/combo-items",
        json=[
            {"component_product_id": bidon["id"], "quantity": 2},
            {"component_product_id": pack["id"], "quantity": 1},
        ],
        headers=headers,
    )
    assert replace_response.status_code == 200, replace_response.text
    items = replace_response.json()
    assert {(i["component_product_id"], i["quantity"]) for i in items} == {
        (bidon["id"], 2),
        (pack["id"], 1),
    }

    get_response = await client.get(f"/api/v1/products/{combo['id']}", headers=headers)
    assert len(get_response.json()["combo_items"]) == 2

    # Replacing again with a smaller set must drop the removed row, not just add.
    replace_again = await client.put(
        f"/api/v1/products/{combo['id']}/combo-items",
        json=[{"component_product_id": bidon["id"], "quantity": 3}],
        headers=headers,
    )
    assert replace_again.status_code == 200
    assert len(replace_again.json()) == 1


async def test_combo_items_rejects_product_not_marked_as_combo(client: AsyncClient):
    tokens = await register_business(client, business_name="Catalogo Combo2", email="combo2@example.com")
    headers = _auth(tokens["access_token"])
    product = (
        await client.post(
            "/api/v1/products", json={"name": "Normal", "price": 100, "unit": "unidad"}, headers=headers
        )
    ).json()
    other = (
        await client.post(
            "/api/v1/products", json={"name": "Otro", "price": 100, "unit": "unidad"}, headers=headers
        )
    ).json()

    response = await client.put(
        f"/api/v1/products/{product['id']}/combo-items",
        json=[{"component_product_id": other["id"], "quantity": 1}],
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "not_a_combo"


async def test_combo_items_rejects_self_reference(client: AsyncClient):
    tokens = await register_business(client, business_name="Catalogo Combo3", email="combo3@example.com")
    headers = _auth(tokens["access_token"])
    combo = (
        await client.post(
            "/api/v1/products",
            json={"name": "Combo", "price": 100, "unit": "combo", "is_combo": True},
            headers=headers,
        )
    ).json()

    response = await client.put(
        f"/api/v1/products/{combo['id']}/combo-items",
        json=[{"component_product_id": combo["id"], "quantity": 1}],
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "self_reference"


async def test_combo_items_rejects_nested_combo(client: AsyncClient):
    tokens = await register_business(client, business_name="Catalogo Combo4", email="combo4@example.com")
    headers = _auth(tokens["access_token"])
    inner_combo = (
        await client.post(
            "/api/v1/products",
            json={"name": "Combo interno", "price": 100, "unit": "combo", "is_combo": True},
            headers=headers,
        )
    ).json()
    outer_combo = (
        await client.post(
            "/api/v1/products",
            json={"name": "Combo externo", "price": 200, "unit": "combo", "is_combo": True},
            headers=headers,
        )
    ).json()

    response = await client.put(
        f"/api/v1/products/{outer_combo['id']}/combo-items",
        json=[{"component_product_id": inner_combo["id"], "quantity": 1}],
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "nested_combo"


async def test_combo_items_rejects_component_not_found(client: AsyncClient):
    tokens = await register_business(client, business_name="Catalogo Combo5", email="combo5@example.com")
    headers = _auth(tokens["access_token"])
    combo = (
        await client.post(
            "/api/v1/products",
            json={"name": "Combo", "price": 100, "unit": "combo", "is_combo": True},
            headers=headers,
        )
    ).json()

    response = await client.put(
        f"/api/v1/products/{combo['id']}/combo-items",
        json=[{"component_product_id": 999999, "quantity": 1}],
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "component_not_found"


async def test_combo_items_rejects_duplicate_component_in_request(client: AsyncClient):
    tokens = await register_business(client, business_name="Catalogo Combo6", email="combo6@example.com")
    headers = _auth(tokens["access_token"])
    combo = (
        await client.post(
            "/api/v1/products",
            json={"name": "Combo", "price": 100, "unit": "combo", "is_combo": True},
            headers=headers,
        )
    ).json()
    component = (
        await client.post(
            "/api/v1/products", json={"name": "Comp", "price": 100, "unit": "unidad"}, headers=headers
        )
    ).json()

    response = await client.put(
        f"/api/v1/products/{combo['id']}/combo-items",
        json=[
            {"component_product_id": component["id"], "quantity": 1},
            {"component_product_id": component["id"], "quantity": 2},
        ],
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "duplicate_component"


async def test_price_tiers_full_replace_flow(client: AsyncClient):
    tokens = await register_business(client, business_name="Catalogo Tiers", email="tiers1@example.com")
    headers = _auth(tokens["access_token"])
    product = (
        await client.post(
            "/api/v1/products", json={"name": "Bidon", "price": 3000, "unit": "bidon"}, headers=headers
        )
    ).json()

    response = await client.put(
        f"/api/v1/products/{product['id']}/price-tiers",
        json=[{"min_quantity": 10, "unit_price": 2500}, {"min_quantity": 30, "unit_price": 2200}],
        headers=headers,
    )
    assert response.status_code == 200
    assert {(t["min_quantity"], t["unit_price"]) for t in response.json()} == {(10, 2500), (30, 2200)}

    replace_again = await client.put(
        f"/api/v1/products/{product['id']}/price-tiers",
        json=[{"min_quantity": 5, "unit_price": 2800}],
        headers=headers,
    )
    assert replace_again.status_code == 200
    assert len(replace_again.json()) == 1


async def test_price_tiers_rejects_duplicate_min_quantity(client: AsyncClient):
    tokens = await register_business(client, business_name="Catalogo Tiers2", email="tiers2@example.com")
    headers = _auth(tokens["access_token"])
    product = (
        await client.post(
            "/api/v1/products", json={"name": "Bidon", "price": 3000, "unit": "bidon"}, headers=headers
        )
    ).json()

    response = await client.put(
        f"/api/v1/products/{product['id']}/price-tiers",
        json=[{"min_quantity": 10, "unit_price": 2500}, {"min_quantity": 10, "unit_price": 2200}],
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "duplicate_min_quantity"


async def test_driver_role_is_rejected_on_catalog_write_endpoints(client: AsyncClient, db_session):
    """Access-control guarantee requested explicitly, same category as the
    tenant-isolation test: a driver must never be able to write to the
    catalog, and this must be locked in by a test, not just trusted to the
    dependency staying correct."""
    tokens = await register_business(
        client, business_name="Catalogo Driver", email="catalogodriver@example.com"
    )
    me = await _whoami(client, tokens["access_token"])

    driver = await create_user_in_business(
        db_session,
        business_id=me["business_id"],
        role=UserRole.driver,
        email="driver-catalogo@example.com",
    )
    driver_token = create_access_token(driver.id, driver.business_id, UserRole.driver.value)

    create_response = await client.post(
        "/api/v1/products",
        json={"name": "No deberia crear esto", "price": 100, "unit": "unidad"},
        headers=_auth(driver_token),
    )
    assert create_response.status_code == 403
    assert create_response.json()["code"] == "forbidden_role"


async def test_driver_role_can_still_read_the_catalog(client: AsyncClient, db_session):
    """Proves the gating is write-only, not a blanket lockout — a driver needs
    to see product names/prices to render an order's items (Fase 1 app)."""
    tokens = await register_business(
        client, business_name="Catalogo Driver Read", email="catalogodriverread@example.com"
    )
    me = await _whoami(client, tokens["access_token"])
    await client.post(
        "/api/v1/products",
        json={"name": "Visible al repartidor", "price": 100, "unit": "unidad"},
        headers=_auth(tokens["access_token"]),
    )

    driver = await create_user_in_business(
        db_session,
        business_id=me["business_id"],
        role=UserRole.driver,
        email="driver-catalogo-read@example.com",
    )
    driver_token = create_access_token(driver.id, driver.business_id, UserRole.driver.value)

    list_response = await client.get("/api/v1/products", headers=_auth(driver_token))
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
