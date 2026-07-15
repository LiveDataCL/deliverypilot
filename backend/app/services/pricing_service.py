from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tenant import TenantContext, tenant_query
from app.models.product import PriceTier, Product


async def resolve_unit_price(
    db: AsyncSession, ctx: TenantContext, product: Product, quantity: int
) -> int:
    """SPEC.md §4.4: the tier with the greatest min_quantity <= quantity wins;
    no applicable tier falls back to the product's base price. Takes an
    already-loaded Product (callers need it loaded anyway to build the order
    line) rather than a bare product_id, so there's no ambiguity here about
    what happens if the product doesn't exist — that's the caller's problem,
    resolved before calling this."""
    tier = await db.scalar(
        tenant_query(PriceTier, ctx)
        .where(PriceTier.product_id == product.id, PriceTier.min_quantity <= quantity)
        .order_by(PriceTier.min_quantity.desc())
        .limit(1)
    )
    return tier.unit_price if tier is not None else product.price
