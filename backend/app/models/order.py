from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import OrderStatus


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "business_id"],
            ["customers.id", "customers.business_id"],
            name="fk_orders_customer_business",
        ),
        ForeignKeyConstraint(
            ["payment_method_id", "business_id"],
            ["payment_methods.id", "payment_methods.business_id"],
            name="fk_orders_payment_method_business",
        ),
        ForeignKeyConstraint(
            ["driver_id", "business_id"],
            ["drivers.id", "drivers.business_id"],
            name="fk_orders_driver_business",
        ),
        UniqueConstraint("id", "business_id", name="uq_orders_id_business_id"),
        UniqueConstraint("tracking_token", name="uq_orders_tracking_token"),
        Index("ix_orders_business_status", "business_id", "status"),
        Index("ix_orders_business_created_at", "business_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Snapshots — editable independently of the linked customer record.
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    delivery_address: Mapped[str] = mapped_column(String(300), nullable=False)
    delivery_lat: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    delivery_lng: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    pickup_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    pickup_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    pickup_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cash_amount_given: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status"), nullable=False, server_default=OrderStatus.pendiente.value
    )
    driver_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tracking_token: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "business_id"],
            ["orders.id", "orders.business_id"],
            name="fk_order_items_order_business",
        ),
        ForeignKeyConstraint(
            ["product_id", "business_id"],
            ["products.id", "products.business_id"],
            name="fk_order_items_product_business",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False, index=True
    )
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # Nullable: an ad-hoc line item (free-text `description`) not tied to the catalog.
    product_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # Effective unit price actually charged (tier-resolved or manually overridden).
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal: Mapped[int] = mapped_column(Integer, nullable=False)


class OrderEvent(Base):
    """Full audit trail of order state changes — who, when, where. Nothing
    changes an order's status without a row here (Fase 1 state machine)."""

    __tablename__ = "order_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "business_id"],
            ["orders.id", "orders.business_id"],
            name="fk_order_events_order_business",
        ),
        ForeignKeyConstraint(
            ["actor_user_id", "business_id"],
            ["users.id", "users.business_id"],
            name="fk_order_events_actor_business",
        ),
        Index("ix_order_events_business_order", "business_id", "order_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False, index=True
    )
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(SAEnum(OrderStatus, name="order_status"), nullable=False)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
