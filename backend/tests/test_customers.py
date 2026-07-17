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


async def test_create_and_list_customers(client: AsyncClient):
    tokens = await register_business(client, business_name="Clientes A", email="clientesA@example.com")
    create_response = await client.post(
        "/api/v1/customers",
        json={"phone": "+56911111111", "name": "Juan Perez", "address": "Calle Falsa 123"},
        headers=_auth(tokens["access_token"]),
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["name"] == "Juan Perez"
    assert created["order_frequency_days"] is None
    assert created["last_order_at"] is None

    list_response = await client.get("/api/v1/customers", headers=_auth(tokens["access_token"]))
    assert list_response.status_code == 200
    body = list_response.json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["id"]


async def test_get_customer_not_found_returns_404(client: AsyncClient):
    tokens = await register_business(client, business_name="Clientes B", email="clientesB@example.com")
    response = await client.get("/api/v1/customers/999999", headers=_auth(tokens["access_token"]))
    assert response.status_code == 404
    assert response.json()["code"] == "customer_not_found"


async def test_update_customer(client: AsyncClient):
    tokens = await register_business(client, business_name="Clientes C", email="clientesC@example.com")
    created = (
        await client.post(
            "/api/v1/customers",
            json={"phone": "+56922222222", "name": "Maria", "address": "Calle 1"},
            headers=_auth(tokens["access_token"]),
        )
    ).json()

    patch_response = await client.patch(
        f"/api/v1/customers/{created['id']}",
        json={"name": "Maria Actualizada", "notes": "Cliente frecuente"},
        headers=_auth(tokens["access_token"]),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Maria Actualizada"
    assert patch_response.json()["notes"] == "Cliente frecuente"


async def test_customers_are_tenant_isolated(client: AsyncClient):
    tokens_a = await register_business(client, business_name="Clientes D", email="clientesD@example.com")
    tokens_b = await register_business(client, business_name="Clientes E", email="clientesE@example.com")

    customer_b = (
        await client.post(
            "/api/v1/customers",
            json={"phone": "+56933333333", "name": "Cliente de B", "address": "Calle B"},
            headers=_auth(tokens_b["access_token"]),
        )
    ).json()

    get_response = await client.get(
        f"/api/v1/customers/{customer_b['id']}", headers=_auth(tokens_a["access_token"])
    )
    assert get_response.status_code == 404

    patch_response = await client.patch(
        f"/api/v1/customers/{customer_b['id']}",
        json={"name": "Hackeado"},
        headers=_auth(tokens_a["access_token"]),
    )
    assert patch_response.status_code == 404


async def test_create_customer_rejects_duplicate_phone(client: AsyncClient):
    tokens = await register_business(client, business_name="Clientes F", email="clientesF@example.com")
    headers = _auth(tokens["access_token"])
    await client.post(
        "/api/v1/customers",
        json={"phone": "+56944444444", "name": "Primero", "address": "Calle 1"},
        headers=headers,
    )
    response = await client.post(
        "/api/v1/customers",
        json={"phone": "+56944444444", "name": "Segundo", "address": "Calle 2"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "duplicate_phone"


async def test_update_customer_rejects_duplicate_phone(client: AsyncClient):
    tokens = await register_business(client, business_name="Clientes G", email="clientesG@example.com")
    headers = _auth(tokens["access_token"])
    first = (
        await client.post(
            "/api/v1/customers",
            json={"phone": "+56955555555", "name": "Uno", "address": "Calle 1"},
            headers=headers,
        )
    ).json()
    second = (
        await client.post(
            "/api/v1/customers",
            json={"phone": "+56966666666", "name": "Dos", "address": "Calle 2"},
            headers=headers,
        )
    ).json()

    response = await client.patch(
        f"/api/v1/customers/{second['id']}",
        json={"phone": first["phone"]},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "duplicate_phone"


async def test_search_customers_by_phone_prefix_requires_minimum_four_digits(client: AsyncClient):
    tokens = await register_business(client, business_name="Clientes H", email="clientesH@example.com")
    response = await client.get(
        "/api/v1/customers/search", params={"phone_prefix": "123"}, headers=_auth(tokens["access_token"])
    )
    assert response.status_code == 422


async def test_search_customers_by_phone_prefix_matches_national_number(client: AsyncClient):
    tokens = await register_business(client, business_name="Clientes I", email="clientesI@example.com")
    headers = _auth(tokens["access_token"])
    await client.post(
        "/api/v1/customers",
        json={"phone": "+56912345678", "name": "Coincide", "address": "Calle 1"},
        headers=headers,
    )
    await client.post(
        "/api/v1/customers",
        json={"phone": "+56987654321", "name": "No coincide", "address": "Calle 2"},
        headers=headers,
    )

    response = await client.get("/api/v1/customers/search", params={"phone_prefix": "9123"}, headers=headers)
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["name"] == "Coincide"


async def test_driver_role_is_rejected_on_customer_endpoints(client: AsyncClient, db_session):
    """Unlike the catalog (reads open to any authenticated role), no customer
    endpoint is open to driver — reads included — since delivery-relevant
    customer info flows through Order's own snapshot fields, not a direct
    /customers call."""
    tokens = await register_business(
        client, business_name="Clientes Driver", email="clientesdriver@example.com"
    )
    me = await _whoami(client, tokens["access_token"])
    driver = await create_user_in_business(
        db_session,
        business_id=me["business_id"],
        role=UserRole.driver,
        email="driver-clientes@example.com",
    )
    driver_token = create_access_token(driver.id, driver.business_id, UserRole.driver.value)

    create_response = await client.post(
        "/api/v1/customers",
        json={"phone": "+56911112222", "name": "No deberia crear esto", "address": "Calle 1"},
        headers=_auth(driver_token),
    )
    assert create_response.status_code == 403
    assert create_response.json()["code"] == "forbidden_role"

    list_response = await client.get("/api/v1/customers", headers=_auth(driver_token))
    assert list_response.status_code == 403
    assert list_response.json()["code"] == "forbidden_role"
