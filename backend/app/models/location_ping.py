from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LocationPing(Base):
    """GPS history. NOTE: SPEC.md mentions monthly partitioning + 90-day retention
    as a future optimization — not implemented in Fase 0 (no current volume to
    justify it); the retention job is an explicit Fase 4 task."""

    __tablename__ = "location_pings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["driver_id", "business_id"],
            ["drivers.id", "drivers.business_id"],
            name="fk_location_pings_driver_business",
        ),
        Index("ix_location_pings_business_driver_recorded", "business_id", "driver_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False, index=True
    )
    driver_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lat: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    lng: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    speed: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    battery: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
