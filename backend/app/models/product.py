from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("id", "business_id", name="uq_products_id_business_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_combo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ComboItem(Base):
    """A combo is a Product with is_combo=true; its components (and their own
    prices) are listed here, but the combo's own price (on `products.price`) is
    independent — never derived as a sum of components."""

    __tablename__ = "combo_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["combo_product_id", "business_id"],
            ["products.id", "products.business_id"],
            name="fk_combo_items_combo_product_business",
        ),
        ForeignKeyConstraint(
            ["component_product_id", "business_id"],
            ["products.id", "products.business_id"],
            name="fk_combo_items_component_product_business",
        ),
        UniqueConstraint(
            "combo_product_id", "component_product_id", name="uq_combo_items_combo_component"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False, index=True
    )
    combo_product_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    component_product_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)


class PriceTier(Base):
    """Volume pricing: resolve_unit_price() (Fase 1) picks the tier with the
    greatest min_quantity <= the ordered quantity, falling back to products.price."""

    __tablename__ = "price_tiers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "business_id"],
            ["products.id", "products.business_id"],
            name="fk_price_tiers_product_business",
        ),
        UniqueConstraint("product_id", "min_quantity", name="uq_price_tiers_product_min_quantity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    min_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
