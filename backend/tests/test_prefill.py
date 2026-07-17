import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.db.tenant import TenantContext, set_tenant_session
from app.models.customer import Customer
from app.models.enums import OrderStatus
from app.models.order import Order
from app.services.customer_defaults_service import recalculate_customer_defaults
from tests.conftest import create_delivered_order, register_business

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient, *, business_name: str, email: str):
    tokens = await register_business(client, business_name=business_name, email=email)
    headers = _auth(tokens["access_token"])
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    customer = (
        await client.post(
            "/api/v1/customers",
            json={"phone": "+56911112222", "name": "Cliente", "address": "Calle 1"},
            headers=headers,
        )
    ).json()
    payment_method = (
        await client.post(
            "/api/v1/payment-methods", json={"name": "Efectivo", "type": "efectivo"}, headers=headers
        )
    ).json()
    product = (
        await client.post(
            "/api/v1/products", json={"name": "Bidon", "price": 3000, "unit": "bidon"}, headers=headers
        )
    ).json()
    ctx = TenantContext(business_id=me["business_id"], user_id=me["id"], role=me["role"])
    return headers, ctx, customer, payment_method, product


async def test_prefill_for_a_brand_new_customer_has_no_suggestions(client: AsyncClient):
    headers, ctx, customer, payment_method, product = await _setup(
        client, business_name="Prefill A", email="prefillA@example.com"
    )
    response = await client.get(f"/api/v1/customers/{customer['id']}/prefill", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["suggestion_source"] == "last_order"
    assert body["suggested_items"] == []


async def test_prefill_uses_last_order_when_fewer_than_three_delivered_orders(
    client: AsyncClient, db_session
):
    headers, ctx, customer, payment_method, product = await _setup(
        client, business_name="Prefill B", email="prefillB@example.com"
    )
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Only 2 delivered orders -> must use the most recent one directly, not
    # customer_defaults (which isn't even populated here).
    await create_delivered_order(
        db_session,
        business_id=ctx.business_id,
        customer_id=customer["id"],
        payment_method_id=payment_method["id"],
        items=[(product["id"], 2, 3000)],
        delivered_at=base,
    )
    await create_delivered_order(
        db_session,
        business_id=ctx.business_id,
        customer_id=customer["id"],
        payment_method_id=payment_method["id"],
        items=[(product["id"], 7, 3000)],
        delivered_at=base + timedelta(days=5),
    )

    response = await client.get(f"/api/v1/customers/{customer['id']}/prefill", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["suggestion_source"] == "last_order"
    assert len(body["suggested_items"]) == 1
    assert body["suggested_items"][0]["quantity"] == 7  # the most recent order, not the first


async def test_prefill_uses_customer_defaults_when_three_or_more_delivered_orders(
    client: AsyncClient, db_session
):
    headers, ctx, customer, payment_method, product = await _setup(
        client, business_name="Prefill C", email="prefillC@example.com"
    )
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, quantity in enumerate([2, 2, 3]):
        await create_delivered_order(
            db_session,
            business_id=ctx.business_id,
            customer_id=customer["id"],
            payment_method_id=payment_method["id"],
            items=[(product["id"], quantity, 3000)],
            delivered_at=base + timedelta(days=i),
        )
    await recalculate_customer_defaults(db_session, ctx, customer["id"])
    await db_session.commit()

    response = await client.get(f"/api/v1/customers/{customer['id']}/prefill", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["suggestion_source"] == "defaults"
    assert len(body["suggested_items"]) == 1
    assert body["suggested_items"][0]["quantity"] == 2
    assert body["suggested_items"][0]["unit_price"] == 3000


async def test_due_for_reorder_includes_a_customer_past_their_frequency(client: AsyncClient, db_session):
    headers, ctx, customer, payment_method, product = await _setup(
        client, business_name="Reorder A", email="reorderA@example.com"
    )
    await set_tenant_session(db_session, ctx.business_id)
    row = await db_session.get(Customer, customer["id"])
    row.last_order_at = datetime.now(timezone.utc) - timedelta(days=20)
    row.order_frequency_days = Decimal("15")
    await db_session.commit()

    response = await client.get("/api/v1/customers/due-for-reorder", headers=headers)
    assert response.status_code == 200
    ids = [c["id"] for c in response.json()["items"]]
    assert customer["id"] in ids


async def test_due_for_reorder_excludes_a_customer_not_yet_due(client: AsyncClient, db_session):
    headers, ctx, customer, payment_method, product = await _setup(
        client, business_name="Reorder B", email="reorderB@example.com"
    )
    await set_tenant_session(db_session, ctx.business_id)
    row = await db_session.get(Customer, customer["id"])
    row.last_order_at = datetime.now(timezone.utc) - timedelta(days=5)
    row.order_frequency_days = Decimal("15")
    await db_session.commit()

    response = await client.get("/api/v1/customers/due-for-reorder", headers=headers)
    assert response.status_code == 200
    ids = [c["id"] for c in response.json()["items"]]
    assert customer["id"] not in ids


async def test_due_for_reorder_excludes_a_customer_with_an_active_order(client: AsyncClient, db_session):
    headers, ctx, customer, payment_method, product = await _setup(
        client, business_name="Reorder C", email="reorderC@example.com"
    )
    await set_tenant_session(db_session, ctx.business_id)
    row = await db_session.get(Customer, customer["id"])
    row.last_order_at = datetime.now(timezone.utc) - timedelta(days=20)
    row.order_frequency_days = Decimal("15")

    active_order = Order(
        business_id=ctx.business_id,
        customer_id=customer["id"],
        customer_name="Cliente",
        customer_phone="+56911112222",
        delivery_address="Calle 1",
        delivery_lat=Decimal("-33.45"),
        delivery_lng=Decimal("-70.65"),
        amount=3000,
        payment_method_id=payment_method["id"],
        status=OrderStatus.en_ruta,
        tracking_token=secrets.token_hex(16),
    )
    db_session.add(active_order)
    await db_session.commit()

    response = await client.get("/api/v1/customers/due-for-reorder", headers=headers)
    assert response.status_code == 200
    ids = [c["id"] for c in response.json()["items"]]
    assert customer["id"] not in ids
