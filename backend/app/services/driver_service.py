from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tenant import TenantContext, tenant_query
from app.models.driver import Driver


async def list_drivers(db: AsyncSession, ctx: TenantContext) -> list[Driver]:
    """Read-only — see app/schemas/driver.py for why this is deliberately
    the only driver-related function here."""
    return list((await db.scalars(tenant_query(Driver, ctx))).all())
