import statistics
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tenant import TenantContext, set_tenant_session
from app.models.customer import Customer, CustomerDefault
from app.models.enums import OrderStatus
from app.models.order import Order, OrderItem


def _mode_with_recency_tiebreak(quantities_most_recent_first: list[int]) -> int:
    """The most frequent quantity wins; on a tie, the quantity from the most
    recent order among the tied values wins (explicit product decision — an
    arbitrary/alphabetical tiebreak would silently pick a stale quantity)."""
    counts = Counter(quantities_most_recent_first)
    max_count = max(counts.values())
    tied = {q for q, c in counts.items() if c == max_count}
    for q in quantities_most_recent_first:
        if q in tied:
            return q
    raise AssertionError("unreachable: tied is a non-empty subset of the input list")


async def recalculate_customer_defaults(db: AsyncSession, ctx: TenantContext, customer_id: int) -> None:
    """SPEC.md §4.2. Standalone and directly callable — NOT wired to any order
    status-transition trigger yet. That wiring belongs to the pedidos
    checkpoint's state machine, which will call this when an order transitions
    to `entregado`. Callers here are expected to have already inserted the
    delivered orders this reads (tests do so directly; production will do so
    via the not-yet-built order state machine).

    Sets the RLS session variable itself (idempotent if the caller's
    transaction already has it set from `get_tenant_context`) rather than
    assuming it — "standalone and directly callable" means callers can't be
    trusted to have done this in the same still-open transaction, and a
    caller that runs this after its own commit (as tests do, since the
    inserted orders need to be visible to a separate session/connection)
    would otherwise have RLS silently filter out every read here."""
    await set_tenant_session(db, ctx.business_id)

    last_5_orders = list(
        (
            await db.scalars(
                select(Order)
                .where(Order.business_id == ctx.business_id)
                .where(Order.customer_id == customer_id)
                .where(Order.status == OrderStatus.entregado)
                .order_by(Order.delivered_at.desc())
                .limit(5)
            )
        ).all()
    )

    if last_5_orders:
        order_ids = [o.id for o in last_5_orders]
        order_rank = {o.id: rank for rank, o in enumerate(last_5_orders)}
        items = list(
            (
                await db.scalars(
                    select(OrderItem)
                    .where(OrderItem.business_id == ctx.business_id)
                    .where(OrderItem.order_id.in_(order_ids))
                    .where(OrderItem.product_id.is_not(None))
                )
            ).all()
        )
        quantities_by_product: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for item in items:
            quantities_by_product[item.product_id].append((order_rank[item.order_id], item.quantity))

        existing_defaults = list(
            (
                await db.scalars(
                    select(CustomerDefault)
                    .where(CustomerDefault.business_id == ctx.business_id)
                    .where(CustomerDefault.customer_id == customer_id)
                )
            ).all()
        )
        for row in existing_defaults:
            await db.delete(row)
        await db.flush()

        new_defaults = []
        for product_id, ranked_quantities in quantities_by_product.items():
            ranked_quantities.sort(key=lambda rq: rq[0])
            quantities_most_recent_first = [q for _rank, q in ranked_quantities]
            mode_quantity = _mode_with_recency_tiebreak(quantities_most_recent_first)
            new_defaults.append(
                CustomerDefault(
                    business_id=ctx.business_id,
                    customer_id=customer_id,
                    product_id=product_id,
                    quantity=mode_quantity,
                )
            )
        db.add_all(new_defaults)

    last_6_orders = list(
        (
            await db.scalars(
                select(Order)
                .where(Order.business_id == ctx.business_id)
                .where(Order.customer_id == customer_id)
                .where(Order.status == OrderStatus.entregado)
                .order_by(Order.delivered_at.desc())
                .limit(6)
            )
        ).all()
    )

    customer = await db.get(Customer, customer_id)
    assert customer is not None

    if len(last_6_orders) < 3:
        customer.order_frequency_days = None
    else:
        gaps_days = [
            (last_6_orders[i].delivered_at - last_6_orders[i + 1].delivered_at).total_seconds() / 86400
            for i in range(len(last_6_orders) - 1)
        ]
        customer.order_frequency_days = round(statistics.median(gaps_days), 2)

    await db.flush()
