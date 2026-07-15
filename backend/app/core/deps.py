from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.base import async_session_factory
from app.db.tenant import TenantContext, set_tenant_session
from app.models.user import User
from app.services import auth_service

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        async with session.begin():
            yield session


async def get_tenant_context(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> TenantContext:
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Token invalido o expirado", "code": "invalid_token"},
        ) from exc

    if payload.token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Se requiere un access token", "code": "wrong_token_type"},
        )

    # Set the RLS session variable from the *signed* JWT claim before issuing any
    # query in this transaction. The JWT signature already vouches for this
    # business_id (it was minted by us at login for this exact user); RLS's job
    # from here on is to catch any query in this request that forgets to filter,
    # not to re-derive which tenant the caller belongs to.
    await set_tenant_session(db, payload.business_id)

    # Re-checked on every request (not only at token refresh, and shared with
    # /auth/refresh via auth_service.get_active_user) so deactivating a user
    # locks them out immediately, even mid-lifetime of a still-valid access token.
    user = await auth_service.get_active_user(
        db, user_id=payload.user_id, business_id=payload.business_id
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Usuario inactivo o inexistente", "code": "inactive_user"},
        )

    return TenantContext(business_id=user.business_id, user_id=user.id, role=user.role.value)


async def get_current_user(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, ctx.user_id)
    assert user is not None
    return user


def require_role(*allowed_roles: str):
    """Dependency factory: rejects the request with 403 unless the caller's
    role is one of `allowed_roles`. Layered on top of get_tenant_context, so
    it still requires a valid access token first — this only adds a role
    check, it doesn't replace authentication."""

    async def _check(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if ctx.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"detail": "No tienes permiso para esta accion", "code": "forbidden_role"},
            )
        return ctx

    return _check
