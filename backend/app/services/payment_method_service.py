from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tenant import TenantContext, tenant_query
from app.models.payment_method import PaymentMethod
from app.schemas.payment_method import PaymentMethodCreate, PaymentMethodUpdate


async def list_payment_methods(
    db: AsyncSession, ctx: TenantContext, *, limit: int, offset: int, active_only: bool = False
) -> tuple[list[PaymentMethod], int]:
    query = tenant_query(PaymentMethod, ctx)
    if active_only:
        query = query.where(PaymentMethod.active.is_(True))

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(
        (
            await db.scalars(
                query.order_by(PaymentMethod.sort_order, PaymentMethod.id).limit(limit).offset(offset)
            )
        ).all()
    )
    return items, total


async def create_payment_method(
    db: AsyncSession, ctx: TenantContext, data: PaymentMethodCreate
) -> PaymentMethod:
    payment_method = PaymentMethod(business_id=ctx.business_id, **data.model_dump())
    db.add(payment_method)
    await db.flush()
    return payment_method


async def update_payment_method(
    db: AsyncSession, ctx: TenantContext, payment_method_id: int, data: PaymentMethodUpdate
) -> PaymentMethod | None:
    payment_method = await db.scalar(
        tenant_query(PaymentMethod, ctx).where(PaymentMethod.id == payment_method_id)
    )
    if payment_method is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(payment_method, field, value)
    await db.flush()
    return payment_method
