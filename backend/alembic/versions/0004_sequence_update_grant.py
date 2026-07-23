"""Grant deliverypilot_app UPDATE on all sequences — app/seed.py's local-dev
reset needs it, without requiring sequence ownership.

Originally tried `ALTER SEQUENCE ... OWNER TO deliverypilot_app` (see
docs/digital-debt.md), but Postgres flatly refuses to change ownership of a
sequence linked to a table via an identity column:
`FeatureNotSupportedError: cannot change owner of sequence "businesses_id_seq"
... is linked to table "businesses"`. Every id column in this schema is
BigInteger/autoincrement, which SQLAlchemy renders as an identity column on
this Postgres version. That restriction is unconditional, not a missing
grant — ownership transfer was a dead end regardless of privileges.

GRANT UPDATE side-steps it entirely: app/seed.py's `_wipe()` no longer
relies on `TRUNCATE ... RESTART IDENTITY` (which internally performs the
equivalent of `ALTER SEQUENCE ... RESTART`, requiring ownership just like
`OWNER TO` does) — it does a plain TRUNCATE followed by explicit
`setval(seq, 1, false)` calls per sequence, which only needs UPDATE
privilege, not ownership.

Unlike ownership, UPDATE genuinely can be pre-granted via default
privileges for sequences that don't exist yet — so unlike the abandoned
ownership approach, there's no "every future migration must remember this"
caveat here: a future migration that adds a new table's sequence is
covered automatically by the ALTER DEFAULT PRIVILEGES statement below.

Revision ID: 0004_sequence_update_grant
Revises: 0003_staff_invite_fields
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_sequence_update_grant"
down_revision: Union[str, None] = "0003_staff_invite_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("GRANT UPDATE ON ALL SEQUENCES IN SCHEMA public TO deliverypilot_app")
    # No FOR ROLE clause: applies to whichever role executes this migration
    # (deliverypilot locally, neondb_owner on Neon) -- migrations always run
    # as that role, so sequences created by future migrations are covered
    # automatically, no per-migration follow-up needed.
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT UPDATE ON SEQUENCES TO deliverypilot_app")


def downgrade() -> None:
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE UPDATE ON SEQUENCES FROM deliverypilot_app")
    op.execute("REVOKE UPDATE ON ALL SEQUENCES IN SCHEMA public FROM deliverypilot_app")
