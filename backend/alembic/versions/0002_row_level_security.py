"""Row-Level Security — DB-layer defense-in-depth for tenant isolation.

Every table that carries business_id gets ENABLE + FORCE ROW LEVEL SECURITY plus
a single policy comparing business_id to current_business_id(), which reads a
per-transaction session variable (app.current_business_id) set via
`set_config(..., true)` — i.e. SET LOCAL semantics — inside the request's
transaction (see app/db/tenant.py:set_tenant_session). Because it's transaction
scoped, it can never leak across a pooled connection to a later, unrelated
request (verified in tests/test_rls.py).

FORCE is required specifically because the app's own DB role owns these tables
(it ran this migration). Postgres exempts table owners from RLS by default;
without FORCE, every policy below would be a silent no-op for our own queries.

`users` is the deliberate exception: it gets ENABLE but NOT FORCE. Login has to
look a user up by email across all tenants before any business_id is known —
forcing RLS there would make login query zero rows for everyone, since no
session variable is set yet at that point in the request. The policy is still
defined (so a future least-privileged, non-owner DB role would be bound by it),
it just doesn't restrict our current single owning app role on this one table.

Revision ID: 0002_row_level_security
Revises: 0001_initial_schema
Create Date: 2026-07-14

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_row_level_security"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FORCED_TENANT_TABLES = [
    "drivers",
    "customers",
    "products",
    "combo_items",
    "price_tiers",
    "payment_methods",
    "customer_defaults",
    "orders",
    "order_items",
    "order_events",
    "location_pings",
    "proofs",
    "subscriptions",
]


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION current_business_id() RETURNS BIGINT AS $$
            SELECT NULLIF(current_setting('app.current_business_id', true), '')::BIGINT;
        $$ LANGUAGE SQL STABLE;
        """
    )

    for table in FORCED_TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (business_id = current_business_id())
            WITH CHECK (business_id = current_business_id())
            """
        )

    # users: see module docstring for why this one is not forced.
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON users
        USING (business_id = current_business_id())
        WITH CHECK (business_id = current_business_id())
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON users")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")

    for table in FORCED_TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP FUNCTION IF EXISTS current_business_id()")
