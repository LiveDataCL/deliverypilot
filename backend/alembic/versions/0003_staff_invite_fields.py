"""Staff invite/reset-password fields on users — Personal checkpoint.

Two nullable timestamps, both serving distinct purposes:

`invite_accepted_at` — NULL means a staff member has been created but never
completed their invite (no real password set yet); non-null is the moment
they did. Purely a display/state concern (the Personal panel needs a third
status beyond `is_active`'s active/deactivated: "Invitado"). Never touched
by an admin-triggered password reset on an already-accepted user.

`password_token_issued_at` — stamped fresh every time an invite or a
password-reset link is issued, and embedded in the signed JWT handed to the
recipient. Accepting the link requires an exact match between the token's
embedded value and this column — so issuing a new link (a re-sent invite,
or an admin-triggered reset) silently invalidates any older, still-live
link, and using a link successfully clears this column, making it properly
single-use rather than just expiry-bounded.

Revision ID: 0003_staff_invite_fields
Revises: 0002_row_level_security
Create Date: 2026-07-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_staff_invite_fields"
down_revision: Union[str, None] = "0002_row_level_security"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("invite_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users", sa.Column("password_token_issued_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "password_token_issued_at")
    op.drop_column("users", "invite_accepted_at")
