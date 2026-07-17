from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tenant import TenantContext, tenant_query
from app.models.customer import Customer, CustomerDefault
from app.models.enums import OrderStatus
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.schemas.customer import (
    CustomerCreate,
    CustomerDefaultIn,
    CustomerDefaultOut,
    CustomerPrefillOut,
    CustomerUpdate,
    SuggestedItemOut,
)
from app.services.pricing_service import resolve_unit_price

# Non-terminal order states — a customer with any order in one of these is
# not "due for reorder" yet, regardless of what their frequency suggests.
_ACTIVE_ORDER_STATUSES = (
    OrderStatus.pendiente,
    OrderStatus.asignado,
    OrderStatus.aceptado,
    OrderStatus.recogido,
    OrderStatus.en_ruta,
)


class CustomerValidationError(Exception):
    """Raised for business-rule violations the router turns into a 400 with
    the project's standard {"detail", "code"} shape."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


async def _get_customer_or_none(db: AsyncSession, ctx: TenantContext, customer_id: int) -> Customer | None:
    return await db.scalar(tenant_query(Customer, ctx).where(Customer.id == customer_id))


async def _phone_taken_by_another(
    db: AsyncSession, ctx: TenantContext, phone: str, *, exclude_customer_id: int | None = None
) -> bool:
    query = tenant_query(Customer, ctx).where(Customer.phone == phone)
    if exclude_customer_id is not None:
        query = query.where(Customer.id != exclude_customer_id)
    return await db.scalar(query) is not None


async def list_customers(
    db: AsyncSession, ctx: TenantContext, *, limit: int, offset: int, query: str | None = None
) -> tuple[list[Customer], int]:
    q = tenant_query(Customer, ctx)
    if query:
        like = f"%{query}%"
        q = q.where((Customer.name.ilike(like)) | (Customer.phone.ilike(like)))

    total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = list(
        (await db.scalars(q.order_by(Customer.name).limit(limit).offset(offset))).all()
    )
    return items, total


async def search_customers_by_phone_prefix(
    db: AsyncSession, ctx: TenantContext, phone_prefix: str
) -> list[Customer]:
    return list(
        (
            await db.scalars(
                tenant_query(Customer, ctx)
                .where(Customer.phone_national.like(f"{phone_prefix}%"))
                .order_by(Customer.last_order_at.desc().nulls_last())
                .limit(8)
            )
        ).all()
    )


async def get_customer(db: AsyncSession, ctx: TenantContext, customer_id: int) -> Customer | None:
    return await _get_customer_or_none(db, ctx, customer_id)


async def create_customer(db: AsyncSession, ctx: TenantContext, data: CustomerCreate) -> Customer:
    if await _phone_taken_by_another(db, ctx, data.phone):
        raise CustomerValidationError(
            "duplicate_phone", "Ya existe un cliente con ese telefono en este negocio"
        )
    customer = Customer(business_id=ctx.business_id, **data.model_dump())
    db.add(customer)
    await db.flush()
    return customer


async def update_customer(
    db: AsyncSession, ctx: TenantContext, customer_id: int, data: CustomerUpdate
) -> Customer | None:
    customer = await _get_customer_or_none(db, ctx, customer_id)
    if customer is None:
        return None
    updates = data.model_dump(exclude_unset=True)
    new_phone = updates.get("phone")
    if new_phone and new_phone != customer.phone:
        if await _phone_taken_by_another(db, ctx, new_phone, exclude_customer_id=customer.id):
            raise CustomerValidationError(
                "duplicate_phone", "Ya existe un cliente con ese telefono en este negocio"
            )
    for field, value in updates.items():
        setattr(customer, field, value)
    await db.flush()
    return customer


async def list_due_for_reorder(
    db: AsyncSession, ctx: TenantContext, *, limit: int, offset: int
) -> tuple[list[Customer], int]:
    active_order_exists = (
        select(Order.id)
        .where(Order.business_id == ctx.business_id)
        .where(Order.customer_id == Customer.id)
        .where(Order.status.in_(_ACTIVE_ORDER_STATUSES))
        .exists()
    )
    candidates = list(
        (
            await db.scalars(
                tenant_query(Customer, ctx).where(
                    Customer.order_frequency_days.is_not(None),
                    Customer.last_order_at.is_not(None),
                    ~active_order_exists,
                )
            )
        ).all()
    )

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=1)
    due = [
        c
        for c in candidates
        if c.last_order_at + timedelta(days=float(c.order_frequency_days)) <= cutoff
    ]
    due.sort(key=lambda c: c.last_order_at + timedelta(days=float(c.order_frequency_days)))

    total = len(due)
    return due[offset : offset + limit], total


async def get_prefill(db: AsyncSession, ctx: TenantContext, customer_id: int) -> CustomerPrefillOut | None:
    customer = await _get_customer_or_none(db, ctx, customer_id)
    if customer is None:
        return None

    delivered_count = await db.scalar(
        select(func.count())
        .select_from(Order)
        .where(Order.business_id == ctx.business_id)
        .where(Order.customer_id == customer_id)
        .where(Order.status == OrderStatus.entregado)
    ) or 0

    if delivered_count < 3:
        last_order = await db.scalar(
            select(Order)
            .where(Order.business_id == ctx.business_id)
            .where(Order.customer_id == customer_id)
            .where(Order.status == OrderStatus.entregado)
            .order_by(Order.delivered_at.desc())
            .limit(1)
        )
        suggested_items: list[SuggestedItemOut] = []
        if last_order is not None:
            rows = (
                await db.execute(
                    select(OrderItem, Product.name)
                    .join(Product, Product.id == OrderItem.product_id)
                    .where(OrderItem.order_id == last_order.id)
                )
            ).all()
            suggested_items = [
                SuggestedItemOut(
                    product_id=item.product_id,
                    name=name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                )
                for item, name in rows
            ]
        return CustomerPrefillOut(
            customer=customer, suggested_items=suggested_items, suggestion_source="last_order"
        )

    rows = (
        await db.execute(
            select(CustomerDefault, Product)
            .join(Product, Product.id == CustomerDefault.product_id)
            .where(CustomerDefault.customer_id == customer_id)
            .where(CustomerDefault.business_id == ctx.business_id)
        )
    ).all()
    suggested_items = [
        SuggestedItemOut(
            product_id=product.id,
            name=product.name,
            quantity=default.quantity,
            unit_price=await resolve_unit_price(db, ctx, product, default.quantity),
        )
        for default, product in rows
    ]
    return CustomerPrefillOut(
        customer=customer, suggested_items=suggested_items, suggestion_source="defaults"
    )


async def list_customer_defaults(
    db: AsyncSession, ctx: TenantContext, customer_id: int
) -> list[CustomerDefaultOut] | None:
    """The raw customer_defaults table, not /prefill's blended suggestion —
    empty is a normal, expected result (customer has 0 delivered orders yet,
    or was reset via recalculate_customer_defaults's empty-history path),
    not an error."""
    customer = await _get_customer_or_none(db, ctx, customer_id)
    if customer is None:
        return None

    rows = (
        await db.execute(
            select(CustomerDefault, Product)
            .join(Product, Product.id == CustomerDefault.product_id)
            .where(CustomerDefault.customer_id == customer_id)
            .where(CustomerDefault.business_id == ctx.business_id)
        )
    ).all()
    return [
        CustomerDefaultOut(product_id=product.id, name=product.name, quantity=default.quantity)
        for default, product in rows
    ]


async def replace_customer_defaults(
    db: AsyncSession, ctx: TenantContext, customer_id: int, items: list[CustomerDefaultIn]
) -> list[CustomerDefaultOut] | None:
    """Manual edit path (SPEC.md §4.2's "fast-start reference, never
    binding"): full-replace, same pattern as catalog_service.
    replace_combo_items/replace_price_tiers. recalculate_customer_defaults
    will silently overwrite whatever's set here once real delivered-order
    history accumulates — that's intentional, not a bug to guard against."""
    customer = await _get_customer_or_none(db, ctx, customer_id)
    if customer is None:
        return None

    product_ids = [item.product_id for item in items]
    if len(product_ids) != len(set(product_ids)):
        raise CustomerValidationError(
            "duplicate_product", "Un mismo producto aparece mas de una vez"
        )

    products_by_id: dict[int, Product] = {}
    if product_ids:
        products = list(
            (await db.scalars(tenant_query(Product, ctx).where(Product.id.in_(product_ids)))).all()
        )
        products_by_id = {p.id: p for p in products}
        missing = set(product_ids) - products_by_id.keys()
        if missing:
            raise CustomerValidationError(
                "product_not_found", f"Producto(s) no encontrados: {sorted(missing)}"
            )

    existing = list(
        (
            await db.scalars(
                select(CustomerDefault)
                .where(CustomerDefault.business_id == ctx.business_id)
                .where(CustomerDefault.customer_id == customer_id)
            )
        ).all()
    )
    for row in existing:
        await db.delete(row)
    await db.flush()

    new_rows = [
        CustomerDefault(
            business_id=ctx.business_id,
            customer_id=customer_id,
            product_id=item.product_id,
            quantity=item.quantity,
        )
        for item in items
    ]
    db.add_all(new_rows)
    await db.flush()

    return [
        CustomerDefaultOut(
            product_id=item.product_id, name=products_by_id[item.product_id].name, quantity=item.quantity
        )
        for item in items
    ]
