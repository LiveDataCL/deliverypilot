from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import UserRole


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Lets drivers/order_events reference (id, business_id) as a composite FK,
        # so the denormalized business_id on those child tables can never drift
        # from the business_id of the user/driver they point to.
        UniqueConstraint("id", "business_id", name="uq_users_id_business_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False, index=True
    )
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole, name="user_role"), nullable=False)
    # Global unique (not per-business): login is by email alone before the
    # business is known, so two tenants can never share an email.
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    fcm_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # NULL = invited but hasn't set a real password yet (Personal checkpoint).
    # Never touched by a later admin-triggered password reset.
    invite_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Stamped fresh on every invite/reset issuance, embedded in that token's
    # JWT payload, and required to match exactly at accept-time -- makes the
    # link genuinely single-use rather than just expiry-bounded (see
    # migration 0003 for the full reasoning).
    password_token_issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
