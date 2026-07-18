import secrets
from datetime import date as date_type
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ws_manager import manager as ws_manager
from app.db.tenant import TenantContext, tenant_query
from app.models.customer import Customer
from app.models.enums import OrderStatus
from app.models.order import Order, OrderEvent, OrderItem
from app.models.payment_method import PaymentMethod
from app.models.product import Product
from app.schemas.order import OrderCreate, OrderItemIn, OrderItemOut, OrderOut
from app.services.geocoding_service import geocode_address
from app.services.pricing_service import resolve_unit_price

_SANTIAGO_TZ = ZoneInfo("America/Santiago")

_GEOCODING_FAILED_MESSAGE = (
    "No pudimos ubicar la direccion automaticamente. "
    "Intenta nuevamente o ingresa las coordenadas manualmente."
)


class OrderValidationError(Exception):
    """Raised for business-rule violations the router turns into a 400 with
    the project's standard {"detail", "code"} shape."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _santiago_day_bounds_utc(day: date_type) -> tuple[datetime, datetime]:
    """CLAUDE.md §4: everything is stored in UTC, converted to
    America/Santiago only when presenting — "today" for the orders table
    means a Santiago calendar day, not a UTC one."""
    start_local = datetime.combine(day, time.min, tzinfo=_SANTIAGO_TZ)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


async def _ensure_geocoded(
    customer: Customer, *, manual_lat: Decimal | None, manual_lng: Decimal | None
) -> None:
    """Guarantees customer.lat/lng are set before they get snapshotted onto
    an order's NOT NULL delivery_lat/delivery_lng — geocoding on demand and
    caching the result onto the customer (SPEC.md §4.1: "si el cliente ya
    tiene lat/lng, NO volver a geocodificar"), covering both a brand-new
    customer and an existing one that was created without coordinates
    (e.g. via the plain Clientes CRUD, which doesn't require them)."""
    if customer.lat is not None and customer.lng is not None:
        return
    if manual_lat is not None and manual_lng is not None:
        customer.lat, customer.lng = manual_lat, manual_lng
        return
    geocoded = await geocode_address(customer.address)
    if geocoded is None:
        raise OrderValidationError("geocoding_failed", _GEOCODING_FAILED_MESSAGE)
    customer.lat, customer.lng = geocoded


async def _resolve_customer(db: AsyncSession, ctx: TenantContext, data: OrderCreate) -> Customer:
    if data.customer_id is not None:
        customer = await db.scalar(tenant_query(Customer, ctx).where(Customer.id == data.customer_id))
        if customer is None:
            raise OrderValidationError("customer_not_found", "Cliente no encontrado")
        await _ensure_geocoded(customer, manual_lat=None, manual_lng=None)
        return customer

    new = data.new_customer
    assert new is not None  # guaranteed by OrderCreate's model_validator

    # Transparently reuse an existing customer if this phone already exists
    # (explicit product decision — not an error, since the phone genuinely
    # isn't new; erroring here would be a confusing dead-end for the
    # operator over what's likely a race or a skipped search step).
    existing = await db.scalar(tenant_query(Customer, ctx).where(Customer.phone == new.phone))
    if existing is not None:
        await _ensure_geocoded(existing, manual_lat=new.lat, manual_lng=new.lng)
        return existing

    customer = Customer(
        business_id=ctx.business_id,
        phone=new.phone,
        name=new.name,
        address=new.address,
        address_detail=new.address_detail,
    )
    db.add(customer)
    await db.flush()
    await _ensure_geocoded(customer, manual_lat=new.lat, manual_lng=new.lng)
    return customer


async def _resolve_order_items(
    db: AsyncSession, ctx: TenantContext, items: list[OrderItemIn]
) -> list[dict]:
    resolved = []
    for item in items:
        if item.product_id is not None:
            product = await db.scalar(tenant_query(Product, ctx).where(Product.id == item.product_id))
            if product is None:
                raise OrderValidationError(
                    "product_not_found", f"Producto {item.product_id} no encontrado"
                )
            # Operator override wins if given; otherwise auto-resolve via
            # the tier logic (SPEC.md E2E criterion 6).
            unit_price = (
                item.unit_price
                if item.unit_price is not None
                else await resolve_unit_price(db, ctx, product, item.quantity)
            )
            resolved.append(
                {
                    "product_id": product.id,
                    "description": None,
                    "quantity": item.quantity,
                    "unit_price": unit_price,
                    "subtotal": unit_price * item.quantity,
                }
            )
        else:
            resolved.append(
                {
                    "product_id": None,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "subtotal": item.unit_price * item.quantity,
                }
            )
    return resolved


async def create_order(db: AsyncSession, ctx: TenantContext, data: OrderCreate) -> Order:
    customer = await _resolve_customer(db, ctx, data)

    payment_method = await db.scalar(
        tenant_query(PaymentMethod, ctx).where(PaymentMethod.id == data.payment_method_id)
    )
    if payment_method is None:
        raise OrderValidationError("payment_method_not_found", "Metodo de pago no encontrado")

    if payment_method.requires_change and data.cash_amount_given is None:
        raise OrderValidationError(
            "cash_amount_required", "Este metodo de pago requiere indicar con cuanto paga el cliente"
        )

    resolved_items = await _resolve_order_items(db, ctx, data.items)
    amount = sum(item["subtotal"] for item in resolved_items)

    if payment_method.requires_change and data.cash_amount_given < amount:
        raise OrderValidationError(
            "insufficient_cash_amount", "El monto entregado es menor al total del pedido"
        )

    order = Order(
        business_id=ctx.business_id,
        customer_id=customer.id,
        customer_name=customer.name,
        customer_phone=customer.phone,
        delivery_address=customer.address,
        delivery_lat=customer.lat,
        delivery_lng=customer.lng,
        pickup_address=data.pickup_address,
        pickup_lat=data.pickup_lat,
        pickup_lng=data.pickup_lng,
        amount=amount,
        payment_method_id=payment_method.id,
        cash_amount_given=data.cash_amount_given,
        notes=data.notes,
        status=OrderStatus.pendiente,
        tracking_token=secrets.token_hex(16),
    )
    db.add(order)
    await db.flush()

    for item in resolved_items:
        db.add(OrderItem(business_id=ctx.business_id, order_id=order.id, **item))

    db.add(
        OrderEvent(
            business_id=ctx.business_id,
            order_id=order.id,
            status=OrderStatus.pendiente,
            actor_user_id=ctx.user_id,
        )
    )
    await db.flush()

    # Same service-layer-triggers-side-effects precedent as
    # order_state_machine.py's transitions -- SPEC.md §3's "eventos para el
    # panel" explicitly includes "nuevo pedido", not just status changes.
    await ws_manager.broadcast(
        ctx.business_id,
        {"type": "order_created", "order_id": order.id, "status": order.status.value},
    )
    return order


async def _to_order_out(db: AsyncSession, ctx: TenantContext, order: Order) -> OrderOut:
    items = list(
        (await db.scalars(tenant_query(OrderItem, ctx).where(OrderItem.order_id == order.id))).all()
    )
    return OrderOut(
        id=order.id,
        business_id=order.business_id,
        customer_id=order.customer_id,
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        delivery_address=order.delivery_address,
        delivery_lat=order.delivery_lat,
        delivery_lng=order.delivery_lng,
        pickup_address=order.pickup_address,
        pickup_lat=order.pickup_lat,
        pickup_lng=order.pickup_lng,
        amount=order.amount,
        payment_method_id=order.payment_method_id,
        cash_amount_given=order.cash_amount_given,
        notes=order.notes,
        status=order.status,
        driver_id=order.driver_id,
        tracking_token=order.tracking_token,
        created_at=order.created_at,
        assigned_at=order.assigned_at,
        accepted_at=order.accepted_at,
        picked_up_at=order.picked_up_at,
        delivered_at=order.delivered_at,
        items=[OrderItemOut.model_validate(i) for i in items],
    )


async def get_order(db: AsyncSession, ctx: TenantContext, order_id: int) -> OrderOut | None:
    order = await db.scalar(tenant_query(Order, ctx).where(Order.id == order_id))
    if order is None:
        return None
    return await _to_order_out(db, ctx, order)


async def list_orders(
    db: AsyncSession,
    ctx: TenantContext,
    *,
    limit: int,
    offset: int,
    status: OrderStatus | None = None,
    on_date: date_type | None = None,
    customer_id: int | None = None,
) -> tuple[list[OrderOut], int]:
    query = tenant_query(Order, ctx)
    if status is not None:
        query = query.where(Order.status == status)
    if on_date is not None:
        start_utc, end_utc = _santiago_day_bounds_utc(on_date)
        query = query.where(Order.created_at >= start_utc, Order.created_at < end_utc)
    if customer_id is not None:
        query = query.where(Order.customer_id == customer_id)

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    orders = list(
        (
            await db.scalars(query.order_by(Order.created_at.desc()).limit(limit).offset(offset))
        ).all()
    )
    items = [await _to_order_out(db, ctx, o) for o in orders]
    return items, total
