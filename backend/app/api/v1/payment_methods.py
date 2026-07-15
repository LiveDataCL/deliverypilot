from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_tenant_context, require_role
from app.db.tenant import TenantContext
from app.models.enums import UserRole
from app.models.payment_method import PaymentMethod
from app.schemas.common import Page
from app.schemas.payment_method import PaymentMethodCreate, PaymentMethodOut, PaymentMethodUpdate
from app.services import payment_method_service

router = APIRouter(prefix="/payment-methods", tags=["catalog"])

_WRITE_ROLES = (UserRole.business_owner.value, UserRole.dispatcher.value)


@router.get("", response_model=Page[PaymentMethodOut])
async def list_payment_methods(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    active_only: bool = Query(False),
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> Page[PaymentMethodOut]:
    items, total = await payment_method_service.list_payment_methods(
        db, ctx, limit=limit, offset=offset, active_only=active_only
    )
    # Explicit conversion + explicit type parameter: `items` here are raw
    # SQLAlchemy ORM objects, and relying on Page(...) constructed without a
    # concrete type parameter to correctly coerce them via from_attributes
    # isn't something worth trusting without being able to run it.
    return Page[PaymentMethodOut](
        items=[PaymentMethodOut.model_validate(pm) for pm in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=PaymentMethodOut, status_code=status.HTTP_201_CREATED)
async def create_payment_method(
    payload: PaymentMethodCreate,
    ctx: TenantContext = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> PaymentMethod:
    return await payment_method_service.create_payment_method(db, ctx, payload)


@router.patch("/{payment_method_id}", response_model=PaymentMethodOut)
async def update_payment_method(
    payment_method_id: int,
    payload: PaymentMethodUpdate,
    ctx: TenantContext = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> PaymentMethod:
    payment_method = await payment_method_service.update_payment_method(
        db, ctx, payment_method_id, payload
    )
    if payment_method is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Metodo de pago no encontrado", "code": "payment_method_not_found"},
        )
    return payment_method
