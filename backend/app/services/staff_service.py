import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_invite_token, decode_token, hash_password
from app.db.tenant import TenantContext, set_tenant_session, tenant_query
from app.models.driver import Driver
from app.models.enums import DriverStatus, UserRole
from app.models.user import User
from app.schemas.staff import StaffCreate, StaffOut

_MANAGED_ROLES = (UserRole.dispatcher, UserRole.driver)


class StaffValidationError(Exception):
    """Raised for business-rule violations the router turns into a 400 with
    the project's standard {"detail", "code"} shape."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class InviteTokenError(Exception):
    """Raised for anything wrong with an invite/reset link at accept-time —
    invalid signature, wrong token type, or superseded/already-used
    (password_token_issued_at mismatch)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def to_staff_out(user: User, driver: Driver | None) -> StaffOut:
    return StaffOut(
        id=user.id,
        business_id=user.business_id,
        role=user.role.value,
        email=user.email,
        phone=user.phone,
        is_active=user.is_active,
        invite_accepted_at=user.invite_accepted_at,
        created_at=user.created_at,
        vehicle_type=driver.vehicle_type if driver else None,
        driver_status=driver.status.value if driver else None,
    )


async def _issue_password_token(db: AsyncSession, user: User) -> str:
    now = datetime.now(timezone.utc)
    user.password_token_issued_at = now
    await db.flush()
    return create_invite_token(user.id, user.business_id, user.role.value, now)


async def list_staff(db: AsyncSession, ctx: TenantContext) -> list[tuple[User, Driver | None]]:
    users = list(
        (await db.scalars(tenant_query(User, ctx).where(User.role.in_(_MANAGED_ROLES)))).all()
    )
    drivers = list((await db.scalars(tenant_query(Driver, ctx))).all())
    driver_by_user_id = {d.user_id: d for d in drivers}
    return [(u, driver_by_user_id.get(u.id)) for u in users]


async def create_staff(
    db: AsyncSession, ctx: TenantContext, data: StaffCreate
) -> tuple[User, Driver | None, str]:
    existing = await db.scalar(select(User).where(User.email == data.email))
    if existing is not None:
        raise StaffValidationError("email_taken", "Ya existe una cuenta con ese email")

    # Unguessable, never revealed — blocks login via the normal password
    # path until the recipient opens their invite link and sets a real one.
    placeholder_password_hash = hash_password(secrets.token_urlsafe(48))

    user = User(
        business_id=ctx.business_id,
        role=UserRole(data.role),
        email=data.email,
        phone=data.phone,
        password_hash=placeholder_password_hash,
    )
    db.add(user)
    await db.flush()

    driver: Driver | None = None
    if data.role == "driver":
        driver = Driver(
            business_id=ctx.business_id,
            user_id=user.id,
            vehicle_type=data.vehicle_type,
            status=DriverStatus.offline,
        )
        db.add(driver)
        await db.flush()

    token = await _issue_password_token(db, user)
    return user, driver, token


async def _get_managed_staff(db: AsyncSession, ctx: TenantContext, staff_id: int) -> User | None:
    return await db.scalar(
        tenant_query(User, ctx).where(User.id == staff_id, User.role.in_(_MANAGED_ROLES))
    )


async def _driver_for(db: AsyncSession, ctx: TenantContext, user_id: int) -> Driver | None:
    return await db.scalar(tenant_query(Driver, ctx).where(Driver.user_id == user_id))


async def set_active(
    db: AsyncSession, ctx: TenantContext, staff_id: int, is_active: bool
) -> tuple[User, Driver | None] | None:
    user = await _get_managed_staff(db, ctx, staff_id)
    if user is None:
        return None
    user.is_active = is_active
    await db.flush()
    return user, await _driver_for(db, ctx, user.id)


async def reset_password(db: AsyncSession, ctx: TenantContext, staff_id: int) -> str | None:
    user = await _get_managed_staff(db, ctx, staff_id)
    if user is None:
        return None
    return await _issue_password_token(db, user)


async def accept_invite(db: AsyncSession, token: str, new_password: str) -> User:
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise InviteTokenError("invalid_token", "Enlace invalido o expirado") from exc

    if payload.token_type != "invite":
        raise InviteTokenError("wrong_token_type", "Se requiere un enlace de invitacion")

    # Deliberately not tenant-scoped, same reasoning as
    # auth_service.find_by_email: the caller has no session/business_id yet.
    # `users` SELECT is unrestricted at the RLS layer for exactly this kind
    # of pre-authentication lookup (migration 0002).
    user = await db.get(User, payload.user_id)
    if user is None or user.business_id != payload.business_id:
        raise InviteTokenError("invalid_token", "Enlace invalido o expirado")

    # Compares actual datetime VALUES via ==, not their isoformat() strings.
    # String comparison was tried first and looked correct — empirically
    # verified against the real Neon connection (`SHOW TimeZone` = 'GMT'),
    # a round-tripped TIMESTAMPTZ came back with tzinfo=timezone.utc and an
    # identical isoformat() string, full microsecond precision preserved —
    # but that only held because this session's TimeZone happens to render
    # the same as timezone.utc. Postgres stores TIMESTAMPTZ as UTC
    # internally but *returns* it converted to the connection's session
    # TimeZone setting; a different environment/config could print a
    # different (but equal) offset and silently break every legitimate
    # accept with a false token_superseded. datetime.__eq__ correctly
    # compares the instant regardless of which tzinfo it's expressed in,
    # so this is immune to that regardless of what any given connection's
    # session timezone happens to be.
    token_marker = payload.password_token_issued_at
    if token_marker is None:
        raise InviteTokenError(
            "token_superseded", "Este enlace ya fue usado o fue reemplazado por uno mas reciente"
        )
    try:
        token_marker_dt = datetime.fromisoformat(token_marker)
    except ValueError as exc:
        raise InviteTokenError("invalid_token", "Enlace invalido o expirado") from exc

    if user.password_token_issued_at is None or user.password_token_issued_at != token_marker_dt:
        raise InviteTokenError(
            "token_superseded", "Este enlace ya fue usado o fue reemplazado por uno mas reciente"
        )

    # Only writes from here — needs the tenant session set (users' INSERT/
    # UPDATE/DELETE policies are tenant-scoped even though SELECT isn't).
    await set_tenant_session(db, user.business_id)
    user.password_hash = hash_password(new_password)
    user.password_token_issued_at = None
    if user.invite_accepted_at is None:
        user.invite_accepted_at = datetime.now(timezone.utc)
    user.is_active = True
    await db.flush()
    return user
