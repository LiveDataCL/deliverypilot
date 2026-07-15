from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DriverStatus


class Driver(Base):
    __tablename__ = "drivers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "business_id"],
            ["users.id", "users.business_id"],
            name="fk_drivers_user_business",
        ),
        UniqueConstraint("id", "business_id", name="uq_drivers_id_business_id"),
        UniqueConstraint("user_id", name="uq_drivers_user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[DriverStatus] = mapped_column(
        SAEnum(DriverStatus, name="driver_status"), nullable=False, server_default=DriverStatus.offline.value
    )
    last_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    last_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
