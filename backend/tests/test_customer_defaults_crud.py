from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.db.tenant import TenantContext
from app.models.enums import UserRole
from app.services.customer_defaults_service import recalculate_customer_defaults
from tests.conftest import create_delivered_order, create_user_in_business, register_business

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _whoami(client: AsyncClient, access_token: str) -> dict:
    response = await client.get("/api/v1/auth/me", headers=_auth(access_token))
    assert response.status_code == 200
    return response.json()


async def _setup(client: AsyncClient, *, business_name: str, email: str):
    tokens = await register_business(client, business_name=business_name, email=email)
    headers = _auth(tokens["access_token"])
    me = await _whoami(client, tokens["access_token"])
    customer = (
        await client.post(
            "/api/v1/customers",
            json={"phone": "+56911112222", "name": "Cliente", "address": "Calle 1"},
            headers=headers,
        )
    ).json()
    product = (
        await client.post(
            "/api/v1/products", json={"name": "Bidon", "price": 3000, "unit": "bidon"}, headers=headers
        )
    ).json()
    return headers, me, customer, product


async def test_list_customer_defaults_is_empty_for_a_brand_new_customer(client: AsyncClient):
    """A customer that never had 3+ orders has no customer_defaults rows yet
    -- this must be an empty list, not an error, since it's a normal and
    expected state, not an exceptional one."""
    headers, me, customer, product = await _setup(
        client, business_name="Defaults CRUD A", email="defaultscrudA@example.com"
    )
    response = await client.get(f"/api/v1/customers/{customer['id']}/defaults", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_list_customer_defaults_is_empty_after_a_recalculate_reset(
    client: AsyncClient, db_session
):
    """The other reachable empty-list path: a customer whose defaults were
    reset to nothing by recalculate_customer_defaults's zero-delivered-
    orders branch (clientes/autofill checkpoint) -- also a clean empty
    list via this endpoint, not an error."""
    headers, me, customer, product = await _setup(
        client, business_name="Defaults CRUD B", email="defaultscrudB@example.com"
    )
    ctx = TenantContext(business_id=me["business_id"], user_id=me["id"], role=me["role"])
    # Manually seed a stale row the way the earlier checkpoint's regression
    # test did, then recalculate with zero delivered orders to clear it.
    await client.put(
        f"/api/v1/customers/{customer['id']}/defaults",
        json=[{"product_id": product["id"], "quantity": 99}],
        headers=headers,
    )
    await recalculate_customer_defaults(db_session, ctx, customer["id"])
    await db_session.commit()

    response = await client.get(f"/api/v1/customers/{customer['id']}/defaults", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_list_customer_defaults_returns_rows_set_via_recalculate(client: AsyncClient, db_session):
    headers, me, customer, product = await _setup(
        client, business_name="Defaults CRUD C", email="defaultscrudC@example.com"
    )
    ctx = TenantContext(business_id=me["business_id"], user_id=me["id"], role=me["role"])
    pm = (
        await client.post(
            "/api/v1/payment-methods", json={"name": "Efectivo", "type": "efectivo"}, headers=headers
        )
    ).json()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    await create_delivered_order(
        db_session,
        business_id=ctx.business_id,
        customer_id=customer["id"],
        payment_method_id=pm["id"],
        items=[(product["id"], 2, 3000)],
        delivered_at=base,
    )
    await recalculate_customer_defaults(db_session, ctx, customer["id"])
    await db_session.commit()

    response = await client.get(f"/api/v1/customers/{customer['id']}/defaults", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["product_id"] == product["id"]
    assert body[0]["name"] == "Bidon"
    assert body[0]["quantity"] == 2


async def test_replace_customer_defaults_full_replace(client: AsyncClient):
    headers, me, customer, product = await _setup(
        client, business_name="Defaults CRUD D", email="defaultscrudD@example.com"
    )
    other_product = (
        await client.post(
            "/api/v1/products", json={"name": "Pack", "price": 2000, "unit": "pack"}, headers=headers
        )
    ).json()

    first_response = await client.put(
        f"/api/v1/customers/{customer['id']}/defaults",
        json=[{"product_id": product["id"], "quantity": 3}],
        headers=headers,
    )
    assert first_response.status_code == 200, first_response.text
    assert len(first_response.json()) == 1

    second_response = await client.put(
        f"/api/v1/customers/{customer['id']}/defaults",
        json=[{"product_id": other_product["id"], "quantity": 5}],
        headers=headers,
    )
    assert second_response.status_code == 200, second_response.text
    body = second_response.json()
    assert len(body) == 1, "must replace, not accumulate"
    assert body[0]["product_id"] == other_product["id"]
    assert body[0]["quantity"] == 5

    get_response = await client.get(f"/api/v1/customers/{customer['id']}/defaults", headers=headers)
    assert len(get_response.json()) == 1
    assert get_response.json()[0]["product_id"] == other_product["id"]


async def test_replace_customer_defaults_rejects_duplicate_product(client: AsyncClient):
    headers, me, customer, product = await _setup(
        client, business_name="Defaults CRUD E", email="defaultscrudE@example.com"
    )
    response = await client.put(
        f"/api/v1/customers/{customer['id']}/defaults",
        json=[
            {"product_id": product["id"], "quantity": 1},
            {"product_id": product["id"], "quantity": 2},
        ],
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "duplicate_product"


async def test_replace_customer_defaults_rejects_product_not_found(client: AsyncClient):
    headers, me, customer, product = await _setup(
        client, business_name="Defaults CRUD F", email="defaultscrudF@example.com"
    )
    response = await client.put(
        f"/api/v1/customers/{customer['id']}/defaults",
        json=[{"product_id": 999999, "quantity": 1}],
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "product_not_found"


async def test_replace_customer_defaults_rejects_a_cross_tenant_product(client: AsyncClient):
    headers_a, me_a, customer_a, product_a = await _setup(
        client, business_name="Defaults CRUD G", email="defaultscrudG@example.com"
    )
    _, _, _, product_b = await _setup(
        client, business_name="Defaults CRUD G Other", email="defaultscrudGother@example.com"
    )
    response = await client.put(
        f"/api/v1/customers/{customer_a['id']}/defaults",
        json=[{"product_id": product_b["id"], "quantity": 1}],
        headers=headers_a,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "product_not_found"


async def test_customer_defaults_are_tenant_isolated(client: AsyncClient):
    headers_a, me_a, customer_a, product_a = await _setup(
        client, business_name="Defaults CRUD H", email="defaultscrudH@example.com"
    )
    headers_b, me_b, customer_b, product_b = await _setup(
        client, business_name="Defaults CRUD H Other", email="defaultscrudHother@example.com"
    )
    get_response = await client.get(f"/api/v1/customers/{customer_b['id']}/defaults", headers=headers_a)
    assert get_response.status_code == 404

    put_response = await client.put(
        f"/api/v1/customers/{customer_b['id']}/defaults",
        json=[{"product_id": product_b["id"], "quantity": 1}],
        headers=headers_a,
    )
    assert put_response.status_code == 404


async def test_get_customer_defaults_for_nonexistent_customer_404(client: AsyncClient):
    tokens = await register_business(
        client, business_name="Defaults CRUD I", email="defaultscrudI@example.com"
    )
    response = await client.get("/api/v1/customers/999999/defaults", headers=_auth(tokens["access_token"]))
    assert response.status_code == 404
    assert response.json()["code"] == "customer_not_found"


async def test_driver_role_is_rejected_on_customer_defaults_endpoints(client: AsyncClient, db_session):
    headers, me, customer, product = await _setup(
        client, business_name="Defaults CRUD Driver", email="defaultscruddriver@example.com"
    )
    driver = await create_user_in_business(
        db_session,
        business_id=me["business_id"],
        role=UserRole.driver,
        email="driver-defaultscrud@example.com",
    )
    driver_token = create_access_token(driver.id, driver.business_id, UserRole.driver.value)

    get_response = await client.get(
        f"/api/v1/customers/{customer['id']}/defaults", headers=_auth(driver_token)
    )
    assert get_response.status_code == 403
    assert get_response.json()["code"] == "forbidden_role"

    put_response = await client.put(
        f"/api/v1/customers/{customer['id']}/defaults",
        json=[{"product_id": product["id"], "quantity": 1}],
        headers=_auth(driver_token),
    )
    assert put_response.status_code == 403
    assert put_response.json()["code"] == "forbidden_role"
