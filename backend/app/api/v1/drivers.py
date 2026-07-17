from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.db.tenant import TenantContext
from app.models.enums import UserRole
from app.schemas.driver import DriverOut
from app.services import driver_service

router = APIRouter(prefix="/drivers", tags=["drivers"])

_ROLES = (UserRole.business_owner.value, UserRole.dispatcher.value)


@router.get("", response_model=list[DriverOut])
async def list_drivers(
    ctx: TenantContext = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[DriverOut]:
    drivers = await driver_service.list_drivers(db, ctx)
    return [DriverOut.model_validate(d) for d in drivers]
