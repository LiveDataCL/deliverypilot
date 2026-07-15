from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("business_id", "phone", name="uq_customers_business_phone"),
        UniqueConstraint("id", "business_id", name="uq_customers_id_business_id"),
        # Mirrors the raw CREATE INDEX in migration 0001 (varchar_pattern_ops
        # isn't expressible via a plain Index(), but declaring it here too keeps
        # a future `alembic revision --autogenerate` from thinking this index
        # doesn't exist and proposing to drop/recreate it).
        Index(
            "ix_customers_business_phone_national",
            "business_id",
            "phone_national",
            postgresql_ops={"phone_national": "varchar_pattern_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False, index=True
    )
    # Canonical E.164, e.g. +56912345678.
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    # Generated from `phone`, stripping the fixed 3-char "+56" prefix, so the
    # phone-prefix search (Fase 1) can index/match the national number the way
    # an operator actually types it, without needing "+56" typed first.
    # Assumes Chilean E.164 only, matching the product's current single-country scope.
    phone_national: Mapped[str] = mapped_column(
        String(15), Computed("substring(phone from 4)", persisted=True)
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    address_detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_frequency_days: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    last_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CustomerDefault(Base):
    """The customer's 'pedido habitual' — recomputed by
    recalculate_customer_defaults() (Fase 1) on every delivered order."""

    __tablename__ = "customer_defaults"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "business_id"],
            ["customers.id", "customers.business_id"],
            name="fk_customer_defaults_customer_business",
        ),
        ForeignKeyConstraint(
            ["product_id", "business_id"],
            ["products.id", "products.business_id"],
            name="fk_customer_defaults_product_business",
        ),
        UniqueConstraint("customer_id", "product_id", name="uq_customer_defaults_customer_product"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False, index=True
    )
    customer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
