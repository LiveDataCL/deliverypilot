"""Initial schema — all Fase 0 tables.

Every business-owned table carries a denormalized `business_id`, even tables
that only relate to their tenant indirectly through a parent (order_items,
order_events, price_tiers, combo_items, customer_defaults, location_pings,
proofs). Child tables reference their parent via a COMPOSITE foreign key on
(parent_id, business_id) rather than just (parent_id), so business_id can
never drift from the value on the row it points to — enforced by Postgres,
not by application discipline. This is what makes tenant_query() (see
app/db/tenant.py) a single mechanical helper usable on every table without
per-table join logic.

Row-Level Security is added in a separate migration (0002) so this one stays
readable as "the shape of the data".

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


user_role_enum = postgresql.ENUM(
    "admin", "business_owner", "dispatcher", "driver", name="user_role", create_type=False
)
driver_status_enum = postgresql.ENUM("offline", "online", "busy", name="driver_status", create_type=False)
payment_method_type_enum = postgresql.ENUM(
    "efectivo", "transferencia", "pos", "online", "otro", name="payment_method_type", create_type=False
)
order_status_enum = postgresql.ENUM(
    "pendiente",
    "asignado",
    "aceptado",
    "recogido",
    "en_ruta",
    "entregado",
    "cancelado",
    "fallido",
    name="order_status",
    create_type=False,
)
proof_type_enum = postgresql.ENUM("photo", "signature", name="proof_type", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    user_role_enum.create(bind, checkfirst=True)
    driver_status_enum.create(bind, checkfirst=True)
    payment_method_type_enum.create(bind, checkfirst=True)
    order_status_enum.create(bind, checkfirst=True)
    proof_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "businesses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("plan", sa.String(50), nullable=False, server_default="piloto"),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="America/Santiago"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CLP"),
        sa.Column(
            "settings_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("role", user_role_enum, nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("fcm_token", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("id", "business_id", name="uq_users_id_business_id"),
    )
    op.create_index("ix_users_business_id", "users", ["business_id"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "drivers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("vehicle_type", sa.String(50), nullable=False),
        sa.Column("status", driver_status_enum, nullable=False, server_default="offline"),
        sa.Column("last_lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("last_lng", sa.Numeric(9, 6), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id", "business_id"],
            ["users.id", "users.business_id"],
            name="fk_drivers_user_business",
        ),
        sa.UniqueConstraint("id", "business_id", name="uq_drivers_id_business_id"),
        sa.UniqueConstraint("user_id", name="uq_drivers_user_id"),
    )
    op.create_index("ix_drivers_business_id", "drivers", ["business_id"])

    op.create_table(
        "customers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column(
            "phone_national",
            sa.String(15),
            sa.Computed("substring(phone from 4)", persisted=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.String(300), nullable=False),
        sa.Column("address_detail", sa.String(200), nullable=True),
        sa.Column("lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("lng", sa.Numeric(9, 6), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_frequency_days", sa.Numeric(6, 2), nullable=True),
        sa.Column("last_order_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("business_id", "phone", name="uq_customers_business_phone"),
        sa.UniqueConstraint("id", "business_id", name="uq_customers_id_business_id"),
    )
    op.create_index("ix_customers_business_id", "customers", ["business_id"])
    op.execute(
        "CREATE INDEX ix_customers_business_phone_national "
        "ON customers (business_id, phone_national varchar_pattern_ops)"
    )

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_combo", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("id", "business_id", name="uq_products_id_business_id"),
    )
    op.create_index("ix_products_business_id", "products", ["business_id"])

    op.create_table(
        "combo_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("combo_product_id", sa.BigInteger(), nullable=False),
        sa.Column("component_product_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["combo_product_id", "business_id"],
            ["products.id", "products.business_id"],
            name="fk_combo_items_combo_product_business",
        ),
        sa.ForeignKeyConstraint(
            ["component_product_id", "business_id"],
            ["products.id", "products.business_id"],
            name="fk_combo_items_component_product_business",
        ),
        sa.UniqueConstraint(
            "combo_product_id", "component_product_id", name="uq_combo_items_combo_component"
        ),
    )
    op.create_index("ix_combo_items_business_id", "combo_items", ["business_id"])

    op.create_table(
        "price_tiers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("min_quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id", "business_id"],
            ["products.id", "products.business_id"],
            name="fk_price_tiers_product_business",
        ),
        sa.UniqueConstraint("product_id", "min_quantity", name="uq_price_tiers_product_min_quantity"),
    )
    op.create_index("ix_price_tiers_business_id", "price_tiers", ["business_id"])

    op.create_table(
        "payment_methods",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("type", payment_method_type_enum, nullable=False),
        sa.Column("requires_change", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("id", "business_id", name="uq_payment_methods_id_business_id"),
    )
    op.create_index("ix_payment_methods_business_id", "payment_methods", ["business_id"])

    op.create_table(
        "customer_defaults",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id", "business_id"],
            ["customers.id", "customers.business_id"],
            name="fk_customer_defaults_customer_business",
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "business_id"],
            ["products.id", "products.business_id"],
            name="fk_customer_defaults_product_business",
        ),
        sa.UniqueConstraint("customer_id", "product_id", name="uq_customer_defaults_customer_product"),
    )
    op.create_index("ix_customer_defaults_business_id", "customer_defaults", ["business_id"])

    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=True),
        sa.Column("external_ref", sa.String(100), nullable=True),
        sa.Column("customer_name", sa.String(200), nullable=False),
        sa.Column("customer_phone", sa.String(20), nullable=False),
        sa.Column("delivery_address", sa.String(300), nullable=False),
        sa.Column("delivery_lat", sa.Numeric(9, 6), nullable=False),
        sa.Column("delivery_lng", sa.Numeric(9, 6), nullable=False),
        sa.Column("pickup_address", sa.String(300), nullable=True),
        sa.Column("pickup_lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("pickup_lng", sa.Numeric(9, 6), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("payment_method_id", sa.BigInteger(), nullable=False),
        sa.Column("cash_amount_given", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", order_status_enum, nullable=False, server_default="pendiente"),
        sa.Column("driver_id", sa.BigInteger(), nullable=True),
        sa.Column("tracking_token", sa.String(64), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id", "business_id"],
            ["customers.id", "customers.business_id"],
            name="fk_orders_customer_business",
        ),
        sa.ForeignKeyConstraint(
            ["payment_method_id", "business_id"],
            ["payment_methods.id", "payment_methods.business_id"],
            name="fk_orders_payment_method_business",
        ),
        sa.ForeignKeyConstraint(
            ["driver_id", "business_id"],
            ["drivers.id", "drivers.business_id"],
            name="fk_orders_driver_business",
        ),
        sa.UniqueConstraint("id", "business_id", name="uq_orders_id_business_id"),
        sa.UniqueConstraint("tracking_token", name="uq_orders_tracking_token"),
    )
    op.create_index("ix_orders_business_id", "orders", ["business_id"])
    op.create_index("ix_orders_business_status", "orders", ["business_id", "status"])
    op.create_index("ix_orders_business_created_at", "orders", ["business_id", "created_at"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Integer(), nullable=False),
        sa.Column("subtotal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id", "business_id"],
            ["orders.id", "orders.business_id"],
            name="fk_order_items_order_business",
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "business_id"],
            ["products.id", "products.business_id"],
            name="fk_order_items_product_business",
        ),
    )
    op.create_index("ix_order_items_business_id", "order_items", ["business_id"])
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    op.create_table(
        "order_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("status", order_status_enum, nullable=False),
        sa.Column("lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("lng", sa.Numeric(9, 6), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["order_id", "business_id"],
            ["orders.id", "orders.business_id"],
            name="fk_order_events_order_business",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id", "business_id"],
            ["users.id", "users.business_id"],
            name="fk_order_events_actor_business",
        ),
    )
    op.create_index("ix_order_events_business_id", "order_events", ["business_id"])
    op.create_index("ix_order_events_business_order", "order_events", ["business_id", "order_id"])

    op.create_table(
        "location_pings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("driver_id", sa.BigInteger(), nullable=False),
        sa.Column("lat", sa.Numeric(9, 6), nullable=False),
        sa.Column("lng", sa.Numeric(9, 6), nullable=False),
        sa.Column("speed", sa.Numeric(6, 2), nullable=True),
        sa.Column("battery", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["driver_id", "business_id"],
            ["drivers.id", "drivers.business_id"],
            name="fk_location_pings_driver_business",
        ),
    )
    op.create_index("ix_location_pings_business_id", "location_pings", ["business_id"])
    op.create_index(
        "ix_location_pings_business_driver_recorded",
        "location_pings",
        ["business_id", "driver_id", "recorded_at"],
    )

    op.create_table(
        "proofs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("type", proof_type_enum, nullable=False),
        sa.Column("file_url", sa.String(500), nullable=False),
        sa.Column("receiver_name", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["order_id", "business_id"],
            ["orders.id", "orders.business_id"],
            name="fk_proofs_order_business",
        ),
    )
    op.create_index("ix_proofs_business_id", "proofs", ["business_id"])
    op.create_index("ix_proofs_order_id", "proofs", ["order_id"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("plan", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("price_clp", sa.Integer(), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_subscriptions_business_id", "subscriptions", ["business_id"])


def downgrade() -> None:
    op.drop_table("subscriptions")
    op.drop_table("proofs")
    op.drop_table("location_pings")
    op.drop_table("order_events")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("customer_defaults")
    op.drop_table("payment_methods")
    op.drop_table("price_tiers")
    op.drop_table("combo_items")
    op.drop_table("products")
    op.drop_table("customers")
    op.drop_table("drivers")
    op.drop_table("users")
    op.drop_table("businesses")

    bind = op.get_bind()
    proof_type_enum.drop(bind, checkfirst=True)
    order_status_enum.drop(bind, checkfirst=True)
    payment_method_type_enum.drop(bind, checkfirst=True)
    driver_status_enum.drop(bind, checkfirst=True)
    user_role_enum.drop(bind, checkfirst=True)
