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


async def test_create_and_list_payment_methods(client: AsyncClient):
    tokens = await register_business(client, business_name="Pagos A", email="pagosA@example.com")
    create_response = await client.post(
        "/api/v1/payment-methods",
        json={"name": "Efectivo", "type": "efectivo", "requires_change": True},
        headers=_auth(tokens["access_token"]),
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["requires_change"] is True

    list_response = await client.get("/api/v1/payment-methods", headers=_auth(tokens["access_token"]))
    assert list_response.status_code == 200
    body = list_response.json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert body["total"] == 1


async def test_deactivating_a_payment_method_does_not_delete_it(client: AsyncClient):
    tokens = await register_business(client, business_name="Pagos B", email="pagosB@example.com")
    created = (
        await client.post(
            "/api/v1/payment-methods",
            json={"name": "Transferencia", "type": "transferencia"},
            headers=_auth(tokens["access_token"]),
        )
    ).json()

    patch_response = await client.patch(
        f"/api/v1/payment-methods/{created['id']}",
        json={"active": False},
        headers=_auth(tokens["access_token"]),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["active"] is False

    list_response = await client.get(
        "/api/v1/payment-methods?active_only=false", headers=_auth(tokens["access_token"])
    )
    assert any(pm["id"] == created["id"] for pm in list_response.json()["items"])


async def test_payment_methods_are_tenant_isolated(client: AsyncClient):
    tokens_a = await register_business(client, business_name="Pagos C", email="pagosC@example.com")
    tokens_b = await register_business(client, business_name="Pagos D", email="pagosD@example.com")

    method_b = (
        await client.post(
            "/api/v1/payment-methods",
            json={"name": "POS de B", "type": "pos"},
            headers=_auth(tokens_b["access_token"]),
        )
    ).json()

    patch_response = await client.patch(
        f"/api/v1/payment-methods/{method_b['id']}",
        json={"active": False},
        headers=_auth(tokens_a["access_token"]),
    )
    assert patch_response.status_code == 404


async def test_driver_role_is_rejected_on_payment_method_writes(client: AsyncClient, db_session):
    tokens = await register_business(
        client, business_name="Pagos Driver", email="pagosdriver@example.com"
    )
    me = await _whoami(client, tokens["access_token"])
    driver = await create_user_in_business(
        db_session,
        business_id=me["business_id"],
        role=UserRole.driver,
        email="driver-pagos@example.com",
    )
    driver_token = create_access_token(driver.id, driver.business_id, UserRole.driver.value)

    response = await client.post(
        "/api/v1/payment-methods",
        json={"name": "No deberia crear esto", "type": "otro"},
        headers=_auth(driver_token),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden_role"
