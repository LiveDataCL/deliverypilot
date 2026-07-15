"""Row-Level Security (migration 0002) as a mechanism independent of the
application: these tests deliberately bypass tenant_query() and write raw,
unfiltered queries — the kind a bug in a service function would produce — to
prove Postgres itself refuses to return another tenant's rows, not just that
our own helper remembers to filter.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.tenant import set_tenant_session
from app.models.business import Business
from app.models.product import Product

pytestmark = pytest.mark.asyncio


async def _make_business_with_product(
    session: AsyncSession, *, business_name: str, product_name: str
) -> tuple[int, int]:
    business = Business(name=business_name)
    session.add(business)
    await session.flush()

    # Product is FORCE-RLS'd (migration 0002): this INSERT's WITH CHECK would
    # reject it if the session variable weren't set to this exact business_id.
    await set_tenant_session(session, business.id)
    product = Product(business_id=business.id, name=product_name, price=1000, unit="unidad")
    session.add(product)
    await session.flush()
    await session.commit()
    return business.id, product.id


async def test_rls_blocks_cross_tenant_select_even_without_an_app_level_filter(db_session: AsyncSession):
    business_a_id, product_a_id = await _make_business_with_product(
        db_session, business_name="RLS Tenant A", product_name="Producto A"
    )
    business_b_id, product_b_id = await _make_business_with_product(
        db_session, business_name="RLS Tenant B", product_name="Producto B"
    )

    await set_tenant_session(db_session, business_a_id)
    # Deliberately unfiltered — no `.where(Product.business_id == ...)` — this
    # is what a service function that forgot tenant_query() would look like.
    visible_ids = (await db_session.scalars(select(Product.id))).all()
    assert product_a_id in visible_ids
    assert product_b_id not in visible_ids

    await set_tenant_session(db_session, business_b_id)
    visible_ids = (await db_session.scalars(select(Product.id))).all()
    assert product_b_id in visible_ids
    assert product_a_id not in visible_ids


async def test_rls_session_variable_does_not_leak_across_pooled_connections():
    """Simulates two sequential HTTP requests sharing a pooled physical
    connection: request 1 sets the tenant and commits; request 2 opens a brand
    new session/transaction and must see nothing. This is what proves
    set_config(..., true) (SET LOCAL semantics) doesn't survive past the
    transaction that set it — required because a connection pool can and will
    hand that same physical connection to a completely unrelated later request.

    Uses a dedicated pool_size=1 engine so the same physical connection is
    deterministically reused between the two sessions below, rather than
    hoping the shared app engine's pool happens to reuse it.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_size=1, max_overflow=0)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as setup_session:
            business_id, product_id = await _make_business_with_product(
                setup_session, business_name="RLS Pool Tenant", product_name="Producto Pool"
            )

        async with session_factory() as session_1:
            await set_tenant_session(session_1, business_id)
            visible = (await session_1.scalars(select(Product.id))).all()
            assert product_id in visible
            await session_1.commit()

        # Fresh session/transaction, deliberately NOT calling set_tenant_session
        # at all. If the pool handed back the same physical connection (forced
        # by pool_size=1 above), this proves it did not inherit request 1's
        # tenant — current_business_id() falls back to NULL, and NULL = anything
        # is false, so this must return zero rows, not business_id's rows.
        async with session_factory() as session_2:
            visible = (await session_2.scalars(select(Product.id))).all()
            assert product_id not in visible
            assert visible == []
    finally:
        await engine.dispose()
