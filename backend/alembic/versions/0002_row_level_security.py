"""Row-Level Security — DB-layer defense-in-depth for tenant isolation.

Every table that carries business_id gets ENABLE + FORCE ROW LEVEL SECURITY plus
a single policy comparing business_id to current_business_id(), which reads a
per-transaction session variable (app.current_business_id) set via
`set_config(..., true)` — i.e. SET LOCAL semantics — inside the request's
transaction (see app/db/tenant.py:set_tenant_session). Because it's transaction
scoped, it can never leak across a pooled connection to a later, unrelated
request (verified in tests/test_rls.py).

FORCE is what makes these policies apply to a table's OWNER too — by default
Postgres exempts owners from RLS. The app's runtime role (deliverypilot_app,
see db/init/01-create-app-role.sql) does NOT own these tables (the migrations
role, deliverypilot, does), so as a non-owner it's already bound by RLS with
or without FORCE. FORCE is kept anyway as a second line of defense, in case
anything is ever run as the owning/migrations role against real data.

`users` needs different treatment, not just an exemption: login has to look a
user up by email across all tenants, before any business_id is known, and a
single business_id-matching policy would apply to SELECT too and return zero
rows for that lookup (current_business_id() isn't set yet at that point).
So `users` gets per-command policies instead of one blanket one: SELECT is
unrestricted at the DB layer (the app must still filter reads by business_id
itself wherever tenant scoping actually matters, e.g. a future "Personal"
listing endpoint — this only removes the DB-layer backstop for that one
command), while INSERT/UPDATE/DELETE stay tenant-scoped, since every write
path always knows which business_id it's writing for.

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

    # users: see module docstring — per-command policies, not one blanket policy.
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY users_select_unrestricted ON users FOR SELECT USING (true)")
    op.execute(
        "CREATE POLICY users_insert_tenant_scoped ON users FOR INSERT "
        "WITH CHECK (business_id = current_business_id())"
    )
    op.execute(
        "CREATE POLICY users_update_tenant_scoped ON users FOR UPDATE "
        "USING (business_id = current_business_id()) "
        "WITH CHECK (business_id = current_business_id())"
    )
    op.execute(
        "CREATE POLICY users_delete_tenant_scoped ON users FOR DELETE "
        "USING (business_id = current_business_id())"
    )


def downgrade() -> None:
    for policy in (
        "users_select_unrestricted",
        "users_insert_tenant_scoped",
        "users_update_tenant_scoped",
        "users_delete_tenant_scoped",
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON users")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")

    for table in FORCED_TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP FUNCTION IF EXISTS current_business_id()")
