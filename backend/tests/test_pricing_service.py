"""Mandated by CLAUDE.md §5: 'Servicio de pricing: aplicación correcta de
tramos por volumen.' Matches SPEC.md §4.4's own worked example: bidón CLP
3.000 unitario; desde 10, CLP 2.500; desde 30 (almacenes), CLP 2.200.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tenant import TenantContext, set_tenant_session
from app.models.business import Business
from app.models.product import PriceTier, Product
from app.services.pricing_service import resolve_unit_price

pytestmark = pytest.mark.asyncio


async def _make_business_and_product(
    db_session: AsyncSession, *, business_name: str, base_price: int
) -> tuple[TenantContext, Product]:
    business = Business(name=business_name)
    db_session.add(business)
    await db_session.flush()
    await set_tenant_session(db_session, business.id)

    product = Product(business_id=business.id, name="Bidon 20L", unit="bidon", price=base_price)
    db_session.add(product)
    await db_session.flush()

    ctx = TenantContext(business_id=business.id, user_id=0, role="business_owner")
    return ctx, product


async def test_resolve_unit_price_falls_back_to_base_price_with_no_tiers(db_session: AsyncSession):
    ctx, product = await _make_business_and_product(
        db_session, business_name="Pricing Tenant A", base_price=3000
    )
    assert await resolve_unit_price(db_session, ctx, product, 1) == 3000
    assert await resolve_unit_price(db_session, ctx, product, 100) == 3000


async def test_resolve_unit_price_matches_spec_worked_example(db_session: AsyncSession):
    ctx, product = await _make_business_and_product(
        db_session, business_name="Pricing Tenant B", base_price=3000
    )
    db_session.add_all(
        [
            PriceTier(business_id=ctx.business_id, product_id=product.id, min_quantity=10, unit_price=2500),
            PriceTier(business_id=ctx.business_id, product_id=product.id, min_quantity=30, unit_price=2200),
        ]
    )
    await db_session.flush()

    assert await resolve_unit_price(db_session, ctx, product, 1) == 3000
    assert await resolve_unit_price(db_session, ctx, product, 9) == 3000
    # Exact tier boundaries — "el mayor min_quantity que sea <= cantidad".
    assert await resolve_unit_price(db_session, ctx, product, 10) == 2500
    assert await resolve_unit_price(db_session, ctx, product, 29) == 2500
    assert await resolve_unit_price(db_session, ctx, product, 30) == 2200
    assert await resolve_unit_price(db_session, ctx, product, 1000) == 2200


async def test_resolve_unit_price_never_applies_another_tenants_tier(db_session: AsyncSession):
    ctx_a, product_a = await _make_business_and_product(
        db_session, business_name="Pricing Tenant C", base_price=3000
    )
    ctx_b, product_b = await _make_business_and_product(
        db_session, business_name="Pricing Tenant D", base_price=5000
    )
    # Tenant B has an aggressive tier that would be obviously wrong if it ever
    # leaked into tenant A's resolution.
    db_session.add(
        PriceTier(business_id=ctx_b.business_id, product_id=product_b.id, min_quantity=10, unit_price=1)
    )
    await db_session.flush()

    await set_tenant_session(db_session, ctx_a.business_id)
    assert await resolve_unit_price(db_session, ctx_a, product_a, 10) == 3000
