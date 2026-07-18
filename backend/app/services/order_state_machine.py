from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ws_manager import manager as ws_manager
from app.db.tenant import TenantContext, tenant_query
from app.models.driver import Driver
from app.models.enums import OrderStatus, UserRole
from app.models.order import Order, OrderEvent
from app.models.user import User
from app.services import fcm_service
from app.services.customer_defaults_service import recalculate_customer_defaults

_DISPATCHER_ROLES = (UserRole.business_owner.value, UserRole.dispatcher.value)

# Transitions reachable only from `assign_driver` below (needs a driver_id,
# so it isn't a plain status transition) are deliberately absent here —
# `pendiente -> asignado` is not in this table.
_ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.pendiente: {OrderStatus.cancelado},
    OrderStatus.asignado: {OrderStatus.aceptado, OrderStatus.cancelado, OrderStatus.fallido},
    OrderStatus.aceptado: {OrderStatus.recogido, OrderStatus.cancelado, OrderStatus.fallido},
    OrderStatus.recogido: {OrderStatus.en_ruta, OrderStatus.cancelado, OrderStatus.fallido},
    OrderStatus.en_ruta: {OrderStatus.entregado, OrderStatus.fallido},
    OrderStatus.entregado: set(),
    OrderStatus.cancelado: set(),
    OrderStatus.fallido: set(),
}

_DISPATCHER_ONLY_TRANSITIONS = {OrderStatus.cancelado}
_DRIVER_ONLY_TRANSITIONS = {
    OrderStatus.aceptado,
    OrderStatus.recogido,
    OrderStatus.en_ruta,
    OrderStatus.entregado,
    OrderStatus.fallido,
}

_TIMESTAMP_FIELD = {
    OrderStatus.aceptado: "accepted_at",
    OrderStatus.recogido: "picked_up_at",
    OrderStatus.entregado: "delivered_at",
}


class InvalidTransitionError(Exception):
    """A 400 — the transition itself doesn't make sense from the order's
    current state, regardless of who's asking."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class DriverNotFoundError(Exception):
    """A 404 — driver_id doesn't resolve in this tenant (composite-FK
    backstop at the DB level; this is the proactive service-layer check,
    see docs/digital-debt.md-style reasoning: never let a raw IntegrityError
    surface as a 500)."""


class OrderTransitionForbiddenError(Exception):
    """A 403 — the transition is valid in the abstract, but this caller
    can't perform it: either the wrong role, or a driver who isn't the one
    assigned to this specific order."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


async def assign_driver(
    db: AsyncSession, ctx: TenantContext, order_id: int, driver_id: int
) -> Order | None:
    order = await db.scalar(tenant_query(Order, ctx).where(Order.id == order_id))
    if order is None:
        return None
    if order.status != OrderStatus.pendiente:
        raise InvalidTransitionError(
            "invalid_transition", f"No se puede asignar un pedido en estado {order.status.value}"
        )

    driver = await db.scalar(tenant_query(Driver, ctx).where(Driver.id == driver_id))
    if driver is None:
        raise DriverNotFoundError()

    driver_user = await db.scalar(tenant_query(User, ctx).where(User.id == driver.user_id))
    if driver_user is None or not driver_user.is_active:
        # SPEC.md §4.4: "un repartidor desactivado no puede... recibir
        # asignaciones" — distinct from DriverNotFoundError (the row exists
        # and resolves in-tenant, it's just not eligible right now).
        raise InvalidTransitionError(
            "driver_inactive", "El repartidor esta desactivado y no puede recibir pedidos"
        )

    order.status = OrderStatus.asignado
    order.driver_id = driver.id
    order.assigned_at = datetime.now(timezone.utc)
    db.add(
        OrderEvent(
            business_id=ctx.business_id,
            order_id=order.id,
            status=OrderStatus.asignado,
            actor_user_id=ctx.user_id,
        )
    )
    await db.flush()

    # Side effects of the transition, same precedent as
    # recalculate_customer_defaults below: triggered from the service layer,
    # not the router. A push/broadcast failure must never fail the
    # assignment itself -- fcm_service.send_push and ws_manager.broadcast
    # both degrade to a no-op rather than raising.
    await fcm_service.send_push(
        driver_user.fcm_token,
        title="Nuevo pedido asignado",
        body=f"Tienes un pedido para entregar en {order.delivery_address}",
        data={"type": "order_assigned", "order_id": str(order.id)},
    )
    await ws_manager.broadcast(
        ctx.business_id,
        {
            "type": "order_status_changed",
            "order_id": order.id,
            "status": order.status.value,
            "driver_id": order.driver_id,
        },
    )
    return order


async def transition_order_status(
    db: AsyncSession,
    ctx: TenantContext,
    order_id: int,
    new_status: OrderStatus,
    *,
    lat: Decimal | None = None,
    lng: Decimal | None = None,
    note: str | None = None,
) -> Order | None:
    order = await db.scalar(tenant_query(Order, ctx).where(Order.id == order_id))
    if order is None:
        return None

    allowed_next = _ALLOWED_TRANSITIONS.get(order.status, set())
    if new_status not in allowed_next:
        raise InvalidTransitionError(
            "invalid_transition", f"No se puede pasar de {order.status.value} a {new_status.value}"
        )

    if new_status in _DISPATCHER_ONLY_TRANSITIONS:
        if ctx.role not in _DISPATCHER_ROLES:
            raise OrderTransitionForbiddenError("Solo un despachador puede cancelar un pedido")
    elif new_status in _DRIVER_ONLY_TRANSITIONS:
        if ctx.role != UserRole.driver.value:
            raise OrderTransitionForbiddenError("Solo el repartidor asignado puede avanzar este pedido")
        driver = await db.scalar(tenant_query(Driver, ctx).where(Driver.id == order.driver_id))
        if driver is None or driver.user_id != ctx.user_id:
            raise OrderTransitionForbiddenError("Solo el repartidor asignado puede avanzar este pedido")

    order.status = new_status
    timestamp_field = _TIMESTAMP_FIELD.get(new_status)
    if timestamp_field is not None:
        setattr(order, timestamp_field, datetime.now(timezone.utc))

    db.add(
        OrderEvent(
            business_id=ctx.business_id,
            order_id=order.id,
            status=new_status,
            lat=lat,
            lng=lng,
            note=note,
            actor_user_id=ctx.user_id,
        )
    )
    await db.flush()

    if new_status == OrderStatus.entregado and order.customer_id is not None:
        await recalculate_customer_defaults(db, ctx, order.customer_id)

    await ws_manager.broadcast(
        ctx.business_id,
        {"type": "order_status_changed", "order_id": order.id, "status": order.status.value},
    )

    return order
