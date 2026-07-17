from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_tenant_context, require_role
from app.db.tenant import TenantContext
from app.models.enums import OrderStatus, UserRole
from app.schemas.common import Page
from app.schemas.order import AssignDriverIn, OrderCreate, OrderOut, OrderStatusTransitionIn
from app.services import order_service, order_state_machine
from app.services.order_service import OrderValidationError

router = APIRouter(prefix="/orders", tags=["orders"])

# Reads/create/assign are dispatcher-facing (the orders table + assignment
# action); driver-side transitions are handled by update_order_status below,
# which uses plain get_tenant_context instead — the allowed role depends on
# the target status and, for drivers, order ownership, which doesn't fit a
# single require_role(*roles) gate. See order_state_machine.py.
_DISPATCHER_ROLES = (UserRole.business_owner.value, UserRole.dispatcher.value)


def _order_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"detail": "Pedido no encontrado", "code": "order_not_found"},
    )


def _validation_error(exc: OrderValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail={"detail": exc.message, "code": exc.code}
    )


async def _reload_or_error(db: AsyncSession, ctx: TenantContext, order_id: int) -> OrderOut:
    """Re-fetches the fully-formed OrderOut right after a write to the same
    row in the same transaction — should never be None. An always-enforced
    check rather than a bare assert, same reasoning as
    customer_defaults_service.CustomerNotFoundError: this codepath must not
    silently pass under Python's -O flag even though the input here isn't
    externally supplied."""
    result = await order_service.get_order(db, ctx, order_id)
    if result is None:
        raise RuntimeError(f"Order {order_id} vanished immediately after being written")
    return result


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    ctx: TenantContext = Depends(require_role(*_DISPATCHER_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> OrderOut:
    try:
        order = await order_service.create_order(db, ctx, payload)
    except OrderValidationError as exc:
        raise _validation_error(exc) from exc
    return await _reload_or_error(db, ctx, order.id)


@router.get("", response_model=Page[OrderOut])
async def list_orders(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: OrderStatus | None = Query(None, alias="status"),
    on_date: date | None = Query(None),
    customer_id: int | None = Query(None),
    ctx: TenantContext = Depends(require_role(*_DISPATCHER_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> Page[OrderOut]:
    items, total = await order_service.list_orders(
        db, ctx, limit=limit, offset=offset, status=status_filter, on_date=on_date, customer_id=customer_id
    )
    return Page[OrderOut](items=items, total=total, limit=limit, offset=offset)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    ctx: TenantContext = Depends(require_role(*_DISPATCHER_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> OrderOut:
    order = await order_service.get_order(db, ctx, order_id)
    if order is None:
        raise _order_not_found()
    return order


@router.post("/{order_id}/assign", response_model=OrderOut)
async def assign_driver(
    order_id: int,
    payload: AssignDriverIn,
    ctx: TenantContext = Depends(require_role(*_DISPATCHER_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> OrderOut:
    try:
        order = await order_state_machine.assign_driver(db, ctx, order_id, payload.driver_id)
    except order_state_machine.DriverNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Repartidor no encontrado", "code": "driver_not_found"},
        ) from exc
    except order_state_machine.InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"detail": exc.message, "code": exc.code}
        ) from exc
    if order is None:
        raise _order_not_found()
    return await _reload_or_error(db, ctx, order.id)


@router.patch("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: int,
    payload: OrderStatusTransitionIn,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> OrderOut:
    try:
        order = await order_state_machine.transition_order_status(
            db, ctx, order_id, payload.status, lat=payload.lat, lng=payload.lng, note=payload.note
        )
    except order_state_machine.OrderTransitionForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": exc.message, "code": "forbidden_transition"},
        ) from exc
    except order_state_machine.InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"detail": exc.message, "code": exc.code}
        ) from exc
    if order is None:
        raise _order_not_found()
    return await _reload_or_error(db, ctx, order.id)
