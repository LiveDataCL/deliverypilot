from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.tenant import TenantContext, set_tenant_session
from app.models.customer import Customer, CustomerDefault
from app.services.customer_defaults_service import (
    CustomerNotFoundError,
    recalculate_customer_defaults,
)
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
    return ctx, customer, payment_method, product


async def _customer_defaults(db_session, ctx: TenantContext, customer_id: int) -> list[CustomerDefault]:
    # recalculate_customer_defaults commits internally (via create_delivered_
    # order's own commits before it, and its callers' commits after) — each
    # commit ends the transaction and clears the RLS session var (SET LOCAL),
    # so it must be re-established before every subsequent read here.
    await set_tenant_session(db_session, ctx.business_id)
    return list(
        (
            await db_session.scalars(
                select(CustomerDefault)
                .where(CustomerDefault.business_id == ctx.business_id)
                .where(CustomerDefault.customer_id == customer_id)
            )
        ).all()
    )


async def test_recalculate_defaults_picks_the_clear_mode_quantity(client: AsyncClient, db_session):
    ctx, customer, payment_method, product = await _setup(
        client, business_name="Defaults A", email="defaultsA@example.com"
    )
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, quantity in enumerate([2, 2, 2, 3, 1]):
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

    defaults = await _customer_defaults(db_session, ctx, customer["id"])
    assert len(defaults) == 1
    assert defaults[0].product_id == product["id"]
    assert defaults[0].quantity == 2


async def test_recalculate_defaults_tie_break_prefers_most_recent_order(client: AsyncClient, db_session):
    """Explicit product decision: on a tied mode, the quantity from the most
    recent order among the tied values wins — not just any tied value."""
    ctx, customer, payment_method, product = await _setup(
        client, business_name="Defaults B", email="defaultsB@example.com"
    )
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Oldest -> newest: 2, 3, 2, 3 — a clean 2-vs-2 tie. The most recent
    # (4th/last) order's quantity is 3, so 3 must win, not 2.
    for i, quantity in enumerate([2, 3, 2, 3]):
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

    defaults = await _customer_defaults(db_session, ctx, customer["id"])
    assert len(defaults) == 1
    assert defaults[0].quantity == 3


async def test_recalculate_defaults_only_uses_last_five_orders(client: AsyncClient, db_session):
    ctx, customer, payment_method, product = await _setup(
        client, business_name="Defaults C", email="defaultsC@example.com"
    )
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # 3 old orders at quantity 9 (must be ignored — outside the last 5),
    # then 5 recent orders at quantity 4 (must set the mode to 4, not 9).
    for i, quantity in enumerate([9, 9, 9, 4, 4, 4, 4, 4]):
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

    defaults = await _customer_defaults(db_session, ctx, customer["id"])
    assert len(defaults) == 1
    assert defaults[0].quantity == 4


async def test_recalculate_defaults_replaces_stale_rows_not_just_appends(client: AsyncClient, db_session):
    ctx, customer, payment_method, product = await _setup(
        client, business_name="Defaults D", email="defaultsD@example.com"
    )
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, quantity in enumerate([1, 1, 1]):
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
    first_pass = await _customer_defaults(db_session, ctx, customer["id"])
    assert len(first_pass) == 1 and first_pass[0].quantity == 1

    for i, quantity in enumerate([5, 5, 5]):
        await create_delivered_order(
            db_session,
            business_id=ctx.business_id,
            customer_id=customer["id"],
            payment_method_id=payment_method["id"],
            items=[(product["id"], quantity, 3000)],
            delivered_at=base + timedelta(days=10 + i),
        )
    await recalculate_customer_defaults(db_session, ctx, customer["id"])
    await db_session.commit()

    second_pass = await _customer_defaults(db_session, ctx, customer["id"])
    assert len(second_pass) == 1, "must replace the stale row, not accumulate a second one"
    assert second_pass[0].quantity == 5


async def test_recalculate_defaults_sets_last_order_at_to_the_most_recent_delivery(
    client: AsyncClient, db_session
):
    """last_order_at is read by search ordering and by due-for-reorder's
    filter/sort — nothing else in the codebase writes it, so this is the
    only thing that keeps it correct."""
    ctx, customer, payment_method, product = await _setup(
        client, business_name="Defaults I", email="defaultsI@example.com"
    )
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    most_recent = base + timedelta(days=5)
    await create_delivered_order(
        db_session,
        business_id=ctx.business_id,
        customer_id=customer["id"],
        payment_method_id=payment_method["id"],
        items=[(product["id"], 1, 3000)],
        delivered_at=base,
    )
    await create_delivered_order(
        db_session,
        business_id=ctx.business_id,
        customer_id=customer["id"],
        payment_method_id=payment_method["id"],
        items=[(product["id"], 1, 3000)],
        delivered_at=most_recent,
    )

    await recalculate_customer_defaults(db_session, ctx, customer["id"])
    await db_session.commit()

    await set_tenant_session(db_session, ctx.business_id)
    updated_customer = await db_session.get(Customer, customer["id"])
    assert updated_customer.last_order_at == most_recent


async def test_order_frequency_days_is_null_with_fewer_than_three_orders(client: AsyncClient, db_session):
    ctx, customer, payment_method, product = await _setup(
        client, business_name="Defaults E", email="defaultsE@example.com"
    )
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(2):
        await create_delivered_order(
            db_session,
            business_id=ctx.business_id,
            customer_id=customer["id"],
            payment_method_id=payment_method["id"],
            items=[(product["id"], 1, 3000)],
            delivered_at=base + timedelta(days=i * 10),
        )

    await recalculate_customer_defaults(db_session, ctx, customer["id"])
    await db_session.commit()

    await set_tenant_session(db_session, ctx.business_id)
    updated_customer = await db_session.get(Customer, customer["id"])
    assert updated_customer.order_frequency_days is None


async def test_order_frequency_days_is_the_median_gap_of_the_last_six_orders(
    client: AsyncClient, db_session
):
    ctx, customer, payment_method, product = await _setup(
        client, business_name="Defaults F", email="defaultsF@example.com"
    )
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # 6 orders, 10 days apart -> 5 gaps of exactly 10 days -> median == 10.
    for i in range(6):
        await create_delivered_order(
            db_session,
            business_id=ctx.business_id,
            customer_id=customer["id"],
            payment_method_id=payment_method["id"],
            items=[(product["id"], 1, 3000)],
            delivered_at=base + timedelta(days=i * 10),
        )

    await recalculate_customer_defaults(db_session, ctx, customer["id"])
    await db_session.commit()

    await set_tenant_session(db_session, ctx.business_id)
    updated_customer = await db_session.get(Customer, customer["id"])
    assert updated_customer.order_frequency_days == 10


async def test_recalculate_defaults_raises_for_a_nonexistent_customer(client: AsyncClient, db_session):
    ctx, customer, payment_method, product = await _setup(
        client, business_name="Defaults G", email="defaultsG@example.com"
    )
    with pytest.raises(CustomerNotFoundError):
        await recalculate_customer_defaults(db_session, ctx, 999999)


async def test_recalculate_defaults_clears_stale_rows_when_there_are_no_delivered_orders(
    client: AsyncClient, db_session
):
    """Defensive edge case: recalculate always replaces customer_defaults
    with whatever the current delivered-order history justifies, including
    replacing it with nothing if a customer somehow has zero delivered
    orders (e.g. a future history-reset action) — never leaves stale rows
    from a previous calculation in place."""
    ctx, customer, payment_method, product = await _setup(
        client, business_name="Defaults H", email="defaultsH@example.com"
    )
    await set_tenant_session(db_session, ctx.business_id)
    db_session.add(
        CustomerDefault(
            business_id=ctx.business_id,
            customer_id=customer["id"],
            product_id=product["id"],
            quantity=99,
        )
    )
    await db_session.commit()

    await recalculate_customer_defaults(db_session, ctx, customer["id"])
    await db_session.commit()

    defaults = await _customer_defaults(db_session, ctx, customer["id"])
    assert defaults == []

    await set_tenant_session(db_session, ctx.business_id)
    updated_customer = await db_session.get(Customer, customer["id"])
    assert updated_customer.last_order_at is None
