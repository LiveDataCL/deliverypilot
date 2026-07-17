from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.db.tenant import TenantContext
from app.models.enums import UserRole
from app.schemas.common import Page
from app.schemas.customer import (
    CustomerCreate,
    CustomerDefaultIn,
    CustomerDefaultOut,
    CustomerOut,
    CustomerPrefillOut,
    CustomerUpdate,
)
from app.services import customer_service
from app.services.customer_service import CustomerValidationError

router = APIRouter(prefix="/customers", tags=["customers"])

# Unlike the catalog (reads open to any authenticated role), customer data has
# no spec'd reason for `driver` to access it directly — delivery-relevant
# customer info flows through Order's own snapshot fields instead. So every
# customer endpoint, reads included, is gated to business_owner/dispatcher.
_ROLES = (UserRole.business_owner.value, UserRole.dispatcher.value)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"detail": "Cliente no encontrado", "code": "customer_not_found"},
    )


def _validation_error(exc: CustomerValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail={"detail": exc.message, "code": exc.code}
    )


@router.get("", response_model=Page[CustomerOut])
async def list_customers(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None),
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> Page[CustomerOut]:
    items, total = await customer_service.list_customers(db, ctx, limit=limit, offset=offset, query=q)
    return Page[CustomerOut](items=items, total=total, limit=limit, offset=offset)


@router.get("/search", response_model=list[CustomerOut])
async def search_customers(
    phone_prefix: str = Query(..., min_length=4, pattern=r"^\d+$"),
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerOut]:
    return await customer_service.search_customers_by_phone_prefix(db, ctx, phone_prefix)


@router.get("/due-for-reorder", response_model=Page[CustomerOut])
async def due_for_reorder(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> Page[CustomerOut]:
    items, total = await customer_service.list_due_for_reorder(db, ctx, limit=limit, offset=offset)
    return Page[CustomerOut](items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> CustomerOut:
    try:
        return await customer_service.create_customer(db, ctx, payload)
    except CustomerValidationError as exc:
        raise _validation_error(exc) from exc


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: int,
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> CustomerOut:
    customer = await customer_service.get_customer(db, ctx, customer_id)
    if customer is None:
        raise _not_found()
    return customer


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> CustomerOut:
    try:
        customer = await customer_service.update_customer(db, ctx, customer_id, payload)
    except CustomerValidationError as exc:
        raise _validation_error(exc) from exc
    if customer is None:
        raise _not_found()
    return customer


@router.get("/{customer_id}/prefill", response_model=CustomerPrefillOut)
async def prefill(
    customer_id: int,
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> CustomerPrefillOut:
    result = await customer_service.get_prefill(db, ctx, customer_id)
    if result is None:
        raise _not_found()
    return result


@router.get("/{customer_id}/defaults", response_model=list[CustomerDefaultOut])
async def list_customer_defaults(
    customer_id: int,
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerDefaultOut]:
    result = await customer_service.list_customer_defaults(db, ctx, customer_id)
    if result is None:
        raise _not_found()
    return result


@router.put("/{customer_id}/defaults", response_model=list[CustomerDefaultOut])
async def replace_customer_defaults(
    customer_id: int,
    payload: list[CustomerDefaultIn],
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerDefaultOut]:
    try:
        result = await customer_service.replace_customer_defaults(db, ctx, customer_id, payload)
    except CustomerValidationError as exc:
        raise _validation_error(exc) from exc
    if result is None:
        raise _not_found()
    return result
