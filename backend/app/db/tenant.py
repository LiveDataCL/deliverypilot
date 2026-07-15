from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy import Select, select, text
from sqlalchemy.ext.asyncio import AsyncSession

ModelT = TypeVar("ModelT")


@dataclass(frozen=True)
class TenantContext:
    """The only source of `business_id` for a request. Never accept business_id
    from a client-supplied path/query/body param for tenant-scoped endpoints —
    it always comes from here, which is derived from the verified JWT."""

    business_id: int
    user_id: int
    role: str


async def set_tenant_session(session: AsyncSession, business_id: int) -> None:
    """Sets the Postgres session variable the RLS policies read from
    (`current_business_id()`, see migration 0002), scoped to the current
    transaction only.

    `set_config(name, value, is_local=true)` behaves like `SET LOCAL`: the value
    is cleared automatically at the end of the transaction. This is what makes it
    safe under connection pooling — even if the pool hands the same physical
    connection to a different request afterwards, that request starts a new
    transaction and sees no leftover value (verified in tests/test_rls.py).
    """
    await session.execute(
        text("SELECT set_config('app.current_business_id', :business_id, true)"),
        {"business_id": str(business_id)},
    )


def tenant_query(model: type[ModelT], ctx: TenantContext) -> Select:
    """The only sanctioned way to build a SELECT against a tenant-owned table.
    Service code must start every read from here instead of `select(Model)` —
    RLS (migration 0002) is the backstop if this is ever forgotten, not the
    primary mechanism."""
    return select(model).where(model.business_id == ctx.business_id)
