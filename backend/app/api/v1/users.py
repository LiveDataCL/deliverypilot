from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_tenant_context
from app.db.tenant import TenantContext, tenant_query
from app.models.user import User
from app.schemas.user import UserProfileOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}", response_model=UserProfileOut)
async def get_user(
    user_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Minimal read endpoint. Exists in Fase 0 specifically to give the
    mandatory tenant-isolation test (CLAUDE.md §5) a real HTTP resource to hit —
    full Personal CRUD (list, invite by link, activate/deactivate) is Fase 1."""
    user = await db.scalar(tenant_query(User, ctx).where(User.id == user_id))
    if user is None:
        # 404, not 403: don't reveal whether a user_id exists in another tenant.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Usuario no encontrado", "code": "user_not_found"},
        )
    return user
