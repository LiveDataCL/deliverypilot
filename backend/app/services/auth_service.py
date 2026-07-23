from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.db.tenant import set_tenant_session
from app.models.business import Business
from app.models.enums import UserRole
from app.models.user import User


async def find_by_email(db: AsyncSession, email: str) -> User | None:
    # Deliberately not scoped by tenant — the one legitimate cross-tenant lookup
    # in the system, needed because login doesn't know the business yet (see
    # migration 0002's note on why `users` is not FORCE-RLS'd).
    return await db.scalar(select(User).where(User.email == email))


async def get_active_user(db: AsyncSession, *, user_id: int, business_id: int) -> User | None:
    """Shared by the tenant-context dependency (every request) and the
    /auth/refresh endpoint — both need "does this (user_id, business_id) pair
    still exist and is it active", and both must apply the same check so a
    deactivated user is locked out consistently everywhere, not just on one path."""
    user = await db.scalar(select(User).where(User.id == user_id, User.business_id == business_id))
    if user is None or not user.is_active:
        return None
    return user


async def register_business_owner(
    db: AsyncSession, *, business_name: str, email: str, password: str, phone: str | None
) -> User:
    business = Business(name=business_name)
    db.add(business)
    await db.flush()  # assigns business.id

    # Not load-bearing here since `users` isn't FORCE-RLS'd for our owning DB
    # role (see migration 0002), but this is the pattern every other tenant-table
    # write in the app must follow, so it's established here too.
    await set_tenant_session(db, business.id)

    user = User(
        business_id=business.id,
        role=UserRole.business_owner,
        email=email,
        phone=phone,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User | None:
    user = await find_by_email(db, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def update_fcm_token(db: AsyncSession, *, user: User, fcm_token: str) -> User:
    """Self-service device-token registration (driver-app Fase 1 checklist).
    Overwrites unconditionally -- a user only ever has one active device
    registered at a time, so the latest call wins, same as re-logging-in on
    a new phone naturally displacing the old token."""
    user.fcm_token = fcm_token
    await db.flush()
    return user
