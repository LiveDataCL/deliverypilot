"""Demo seed for local development: `poetry run python -m app.seed`.

Only ever meant to run against a local/dev database (see docker-compose.yml /
README.md) — it TRUNCATEs its own tables first so it can be re-run idempotently
while iterating locally. Never point TEST_DATABASE_URL or DATABASE_URL at a
shared/prod database when running this.

Creates one demo business (a Chilean purified-water distributor — the pilot
customer described in SPEC.md), its owner + driver accounts, the Fase 0 catalog
(5 products, 1 combo, volume tiers, 3 payment methods), and 10 customers with
fabricated delivered-order history. The `recalculate_customer_defaults` service
and its exact "last 5 orders, mode quantity" rule are Fase 1 work, so this
script computes `last_order_at` / `order_frequency_days` / `customer_defaults`
directly from the fabricated history instead of calling a service that doesn't
exist yet.
"""
import asyncio
import random
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.base import async_session_factory
from app.db.tenant import set_tenant_session
from app.models.business import Business
from app.models.customer import Customer, CustomerDefault
from app.models.driver import Driver
from app.models.enums import DriverStatus, OrderStatus, PaymentMethodType, UserRole
from app.models.order import Order, OrderEvent, OrderItem
from app.models.payment_method import PaymentMethod
from app.models.product import ComboItem, PriceTier, Product
from app.models.user import User

random.seed(42)

DEMO_BUSINESS_NAME = "Aguas del Sur SpA"
DEMO_OWNER_EMAIL = "duena@aguasdelsur.cl"
DEMO_OWNER_PASSWORD = "CambiarPassword123"
DEMO_DRIVER_EMAIL = "repartidor@aguasdelsur.cl"
DEMO_DRIVER_PASSWORD = "CambiarPassword123"

CUSTOMER_NAMES = [
    "Juana Perez", "Marco Soto", "Camila Reyes", "Luis Fuentes", "Andrea Morales",
    "Pedro Castillo", "Valentina Rojas", "Diego Herrera", "Francisca Vidal", "Ignacio Contreras",
]
COMUNAS = [
    "Nunoa", "Providencia", "La Florida", "Maipu", "San Miguel",
    "Independencia", "Recoleta", "Penalolen", "La Reina", "Macul",
]
FREQUENCY_DAYS = [7, 10, 14, 15, 20, 30, 7, 14, 10, 21]
USUAL_QTY = [2, 1, 3, 2, 1, 5, 2, 2, 1, 4]
N_ORDERS = [6, 5, 4, 6, 3, 5, 6, 4, 5, 4]

BASE_LAT, BASE_LNG = Decimal("-33.45"), Decimal("-70.65")

_ALL_TABLES = (
    "subscriptions, proofs, order_events, order_items, orders, customer_defaults, location_pings, "
    "combo_items, price_tiers, products, payment_methods, customers, drivers, users, businesses"
)


async def _wipe(session: AsyncSession) -> None:
    await session.execute(text(f"TRUNCATE {_ALL_TABLES} RESTART IDENTITY CASCADE"))


async def seed() -> None:
    async with async_session_factory() as session, session.begin():
        await _wipe(session)

        business = Business(name=DEMO_BUSINESS_NAME)
        session.add(business)
        await session.flush()

        # Every subsequent write in this script touches forced-RLS tables
        # (migration 0002) — this must be set before any of them or the
        # WITH CHECK policy rejects the insert.
        await set_tenant_session(session, business.id)

        owner = User(
            business_id=business.id,
            role=UserRole.business_owner,
            email=DEMO_OWNER_EMAIL,
            phone="+56911111111",
            password_hash=hash_password(DEMO_OWNER_PASSWORD),
        )
        driver_user = User(
            business_id=business.id,
            role=UserRole.driver,
            email=DEMO_DRIVER_EMAIL,
            phone="+56922222222",
            password_hash=hash_password(DEMO_DRIVER_PASSWORD),
        )
        session.add_all([owner, driver_user])
        await session.flush()

        driver = Driver(
            business_id=business.id,
            user_id=driver_user.id,
            vehicle_type="moto",
            status=DriverStatus.offline,
        )
        session.add(driver)

        bidon_retornable = Product(
            business_id=business.id,
            name="Bidon 20L retornable",
            unit="bidon",
            price=3000,
            sort_order=1,
            description="Bidon de 20 litros con envase retornable",
        )
        bidon_nuevo = Product(
            business_id=business.id,
            name="Bidon 20L nuevo",
            unit="bidon",
            price=5000,
            sort_order=2,
            description="Bidon de 20 litros, envase nuevo (sin retorno)",
        )
        pack_botellas = Product(
            business_id=business.id,
            name="Pack botellas 500ml (x12)",
            unit="pack",
            price=2500,
            sort_order=3,
        )
        dispensador = Product(
            business_id=business.id, name="Dispensador", unit="unidad", price=15000, sort_order=4
        )
        bomba_manual = Product(
            business_id=business.id, name="Bomba manual", unit="unidad", price=5000, sort_order=5
        )
        combo_hogar = Product(
            business_id=business.id,
            name="Combo Hogar",
            unit="combo",
            price=8500,
            is_combo=True,
            sort_order=0,
            description="2 bidones 20L retornables + 1 pack de botellas 500ml",
        )
        session.add_all(
            [bidon_retornable, bidon_nuevo, pack_botellas, dispensador, bomba_manual, combo_hogar]
        )
        await session.flush()

        session.add_all(
            [
                ComboItem(
                    business_id=business.id,
                    combo_product_id=combo_hogar.id,
                    component_product_id=bidon_retornable.id,
                    quantity=2,
                ),
                ComboItem(
                    business_id=business.id,
                    combo_product_id=combo_hogar.id,
                    component_product_id=pack_botellas.id,
                    quantity=1,
                ),
            ]
        )

        # Volume pricing applies to the retornable bidon — the recurring SKU.
        # Matches SPEC.md §4.4's worked example: CLP 3.000 base, 2.500 from 10+,
        # 2.200 from 30+ (almacenes).
        session.add_all(
            [
                PriceTier(
                    business_id=business.id, product_id=bidon_retornable.id, min_quantity=10, unit_price=2500
                ),
                PriceTier(
                    business_id=business.id, product_id=bidon_retornable.id, min_quantity=30, unit_price=2200
                ),
            ]
        )

        efectivo = PaymentMethod(
            business_id=business.id,
            name="Efectivo",
            type=PaymentMethodType.efectivo,
            requires_change=True,
            sort_order=0,
        )
        transferencia = PaymentMethod(
            business_id=business.id,
            name="Transferencia",
            type=PaymentMethodType.transferencia,
            requires_change=False,
            sort_order=1,
        )
        pos = PaymentMethod(
            business_id=business.id,
            name="POS",
            type=PaymentMethodType.pos,
            requires_change=False,
            sort_order=2,
        )
        session.add_all([efectivo, transferencia, pos])
        await session.flush()
        payment_methods = [efectivo, transferencia, pos]

        now = datetime.now(timezone.utc)

        for i, name in enumerate(CUSTOMER_NAMES):
            subscriber = 10_000_000 + i * 111_111
            phone = f"+569{subscriber:08d}"
            comuna = COMUNAS[i % len(COMUNAS)]
            lat = BASE_LAT + Decimal(i - 5) * Decimal("0.01")
            lng = BASE_LNG + Decimal(i - 5) * Decimal("0.01")

            customer = Customer(
                business_id=business.id,
                phone=phone,
                name=name,
                address=f"Calle Falsa {100 + i}, {comuna}",
                lat=lat,
                lng=lng,
            )
            session.add(customer)
            await session.flush()

            frequency_days = FREQUENCY_DAYS[i]
            usual_qty = USUAL_QTY[i]
            n_orders = N_ORDERS[i]
            unit_price = 2500 if usual_qty >= 10 else 3000

            last_delivered_at = None
            for order_idx in range(n_orders):
                days_ago = (n_orders - order_idx) * frequency_days
                delivered_at = now - timedelta(days=days_ago, hours=random.randint(0, 5))
                created_at = delivered_at - timedelta(hours=2)
                payment_method = payment_methods[(i + order_idx) % len(payment_methods)]
                amount = unit_price * usual_qty

                order = Order(
                    business_id=business.id,
                    customer_id=customer.id,
                    customer_name=customer.name,
                    customer_phone=customer.phone,
                    delivery_address=customer.address,
                    delivery_lat=customer.lat,
                    delivery_lng=customer.lng,
                    amount=amount,
                    payment_method_id=payment_method.id,
                    cash_amount_given=amount if payment_method.requires_change else None,
                    status=OrderStatus.entregado,
                    driver_id=driver.id,
                    tracking_token=secrets.token_hex(16),
                    created_at=created_at,
                    assigned_at=created_at + timedelta(minutes=5),
                    accepted_at=created_at + timedelta(minutes=10),
                    picked_up_at=created_at + timedelta(minutes=20),
                    delivered_at=delivered_at,
                )
                session.add(order)
                await session.flush()

                session.add(
                    OrderItem(
                        business_id=business.id,
                        order_id=order.id,
                        product_id=bidon_retornable.id,
                        quantity=usual_qty,
                        unit_price=unit_price,
                        subtotal=amount,
                    )
                )
                session.add(
                    OrderEvent(
                        business_id=business.id,
                        order_id=order.id,
                        status=OrderStatus.entregado,
                        lat=customer.lat,
                        lng=customer.lng,
                        actor_user_id=driver_user.id,
                        created_at=delivered_at,
                    )
                )
                last_delivered_at = delivered_at

            customer.last_order_at = last_delivered_at
            customer.order_frequency_days = Decimal(frequency_days)
            session.add(
                CustomerDefault(
                    business_id=business.id,
                    customer_id=customer.id,
                    product_id=bidon_retornable.id,
                    quantity=usual_qty,
                )
            )

        seeded_business_id = business.id

    print(f"Seed OK - negocio '{DEMO_BUSINESS_NAME}' (id={seeded_business_id})")
    print(f"  owner:  {DEMO_OWNER_EMAIL} / {DEMO_OWNER_PASSWORD}")
    print(f"  driver: {DEMO_DRIVER_EMAIL} / {DEMO_DRIVER_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
