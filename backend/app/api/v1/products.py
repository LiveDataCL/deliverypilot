from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_tenant_context, require_role
from app.db.tenant import TenantContext
from app.models.enums import UserRole
from app.schemas.common import Page
from app.schemas.product import (
    ComboItemIn,
    ComboItemOut,
    PriceTierIn,
    PriceTierOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from app.services import catalog_service
from app.services.catalog_service import CatalogValidationError

router = APIRouter(prefix="/products", tags=["catalog"])

# Reads are open to any authenticated tenant user (a driver needs product
# names/prices to render an order's items); only writes are gated.
_WRITE_ROLES = (UserRole.business_owner.value, UserRole.dispatcher.value)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"detail": "Producto no encontrado", "code": "product_not_found"},
    )


@router.get("", response_model=Page[ProductOut])
async def list_products(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    active_only: bool = Query(False),
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> Page[ProductOut]:
    items, total = await catalog_service.list_products(
        db, ctx, limit=limit, offset=offset, active_only=active_only
    )
    # Explicit type parameter — see the equivalent note in payment_methods.py.
    return Page[ProductOut](items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    ctx: TenantContext = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ProductOut:
    return await catalog_service.create_product(db, ctx, payload)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> ProductOut:
    product = await catalog_service.get_product(db, ctx, product_id)
    if product is None:
        raise _not_found()
    return product


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    ctx: TenantContext = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ProductOut:
    product = await catalog_service.update_product(db, ctx, product_id, payload)
    if product is None:
        raise _not_found()
    return product


@router.put("/{product_id}/combo-items", response_model=list[ComboItemOut])
async def replace_combo_items(
    product_id: int,
    payload: list[ComboItemIn],
    ctx: TenantContext = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[ComboItemOut]:
    try:
        result = await catalog_service.replace_combo_items(db, ctx, product_id, payload)
    except CatalogValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"detail": exc.message, "code": exc.code}
        ) from exc
    if result is None:
        raise _not_found()
    return result


@router.put("/{product_id}/price-tiers", response_model=list[PriceTierOut])
async def replace_price_tiers(
    product_id: int,
    payload: list[PriceTierIn],
    ctx: TenantContext = Depends(require_role(*_WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[PriceTierOut]:
    try:
        result = await catalog_service.replace_price_tiers(db, ctx, product_id, payload)
    except CatalogValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"detail": exc.message, "code": exc.code}
        ) from exc
    if result is None:
        raise _not_found()
    return result
