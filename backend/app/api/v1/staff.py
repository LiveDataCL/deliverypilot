from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.db.tenant import TenantContext
from app.models.enums import UserRole
from app.schemas.staff import StaffCreate, StaffCreateResponse, StaffOut, ResetPasswordResponse
from app.services import staff_service
from app.services.staff_service import StaffValidationError

router = APIRouter(prefix="/staff", tags=["staff"])

# Same convention as every other checkpoint: writes gated to
# business_owner/dispatcher. business_owner/admin accounts themselves aren't
# manageable through this surface (see staff_service._MANAGED_ROLES).
_ROLES = (UserRole.business_owner.value, UserRole.dispatcher.value)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"detail": "Personal no encontrado", "code": "staff_not_found"},
    )


@router.get("", response_model=list[StaffOut])
async def list_staff(
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[StaffOut]:
    rows = await staff_service.list_staff(db, ctx)
    return [staff_service.to_staff_out(user, driver) for user, driver in rows]


@router.post("", response_model=StaffCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_staff(
    payload: StaffCreate,
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> StaffCreateResponse:
    try:
        user, driver, token = await staff_service.create_staff(db, ctx, payload)
    except StaffValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"detail": exc.message, "code": exc.code}
        ) from exc
    return StaffCreateResponse(staff=staff_service.to_staff_out(user, driver), invite_token=token)


@router.patch("/{staff_id}/activate", response_model=StaffOut)
async def activate(
    staff_id: int,
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> StaffOut:
    result = await staff_service.set_active(db, ctx, staff_id, True)
    if result is None:
        raise _not_found()
    return staff_service.to_staff_out(*result)


@router.patch("/{staff_id}/deactivate", response_model=StaffOut)
async def deactivate(
    staff_id: int,
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> StaffOut:
    result = await staff_service.set_active(db, ctx, staff_id, False)
    if result is None:
        raise _not_found()
    return staff_service.to_staff_out(*result)


@router.post("/{staff_id}/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    staff_id: int,
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ResetPasswordResponse:
    token = await staff_service.reset_password(db, ctx, staff_id)
    if token is None:
        raise _not_found()
    return ResetPasswordResponse(invite_token=token)
