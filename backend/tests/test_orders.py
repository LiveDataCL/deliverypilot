import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.enums import UserRole
from tests.conftest import create_user_in_business, register_business

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _whoami(client: AsyncClient, access_token: str) -> dict:
    response = await client.get("/api/v1/auth/me", headers=_auth(access_token))
    assert response.status_code == 200
    return response.json()


async def _setup(client: AsyncClient, *, business_name: str, email: str):
    tokens = await register_business(client, business_name=business_name, email=email)
    headers = _auth(tokens["access_token"])
    customer = (
        await client.post(
            "/api/v1/customers",
            json={
                "phone": "+56911112222",
                "name": "Cliente",
                "address": "Calle 1",
            },
            headers=headers,
        )
    ).json()
    # Created without coordinates (CustomerCreate has no lat/lng in the UI
    # form); tests that actually create an order call
    # _give_customer_coordinates first to avoid exercising the geocoding
    # fallback here — that's covered separately in
    # test_order_creation_customer_flow.py.
    cash = (
        await client.post(
            "/api/v1/payment-methods",
            json={"name": "Efectivo", "type": "efectivo", "requires_change": True},
            headers=headers,
        )
    ).json()
    transfer = (
        await client.post(
            "/api/v1/payment-methods",
            json={"name": "Transferencia", "type": "transferencia", "requires_change": False},
            headers=headers,
        )
    ).json()
    product = (
        await client.post(
            "/api/v1/products", json={"name": "Bidon", "price": 3000, "unit": "bidon"}, headers=headers
        )
    ).json()
    return headers, customer, cash, transfer, product


async def _give_customer_coordinates(client: AsyncClient, headers: dict, customer_id: int) -> None:
    """CustomerUpdate already supports lat/lng directly — used here so order-
    creation tests exercise order logic, not the geocoding fallback (that's
    covered separately in test_order_creation_customer_flow.py)."""
    response = await client.patch(
        f"/api/v1/customers/{customer_id}", json={"lat": "-33.45", "lng": "-70.65"}, headers=headers
    )
    assert response.status_code == 200, response.text


async def test_create_order_with_existing_customer(client: AsyncClient):
    headers, customer, cash, transfer, product = await _setup(
        client, business_name="Pedidos A", email="pedidosA@example.com"
    )
    await _give_customer_coordinates(client, headers, customer["id"])

    response = await client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 2}],
            "payment_method_id": transfer["id"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["status"] == "pendiente"
    assert order["customer_id"] == customer["id"]
    assert order["amount"] == 6000
    assert len(order["items"]) == 1
    assert order["items"][0]["unit_price"] == 3000
    assert order["items"][0]["subtotal"] == 6000


async def test_create_order_computes_amount_server_side_not_from_client(client: AsyncClient):
    headers, customer, cash, transfer, product = await _setup(
        client, business_name="Pedidos B", email="pedidosB@example.com"
    )
    await _give_customer_coordinates(client, headers, customer["id"])

    response = await client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 3}],
            "payment_method_id": transfer["id"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    # amount isn't even accepted in the payload -- confirm it's always the
    # server-computed 3 * 3000, regardless of anything the client could send.
    assert response.json()["amount"] == 9000


async def test_create_order_with_adhoc_item(client: AsyncClient):
    headers, customer, cash, transfer, product = await _setup(
        client, business_name="Pedidos C", email="pedidosC@example.com"
    )
    await _give_customer_coordinates(client, headers, customer["id"])

    response = await client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"description": "Servicio especial", "quantity": 1, "unit_price": 12000}],
            "payment_method_id": transfer["id"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["amount"] == 12000
    assert order["items"][0]["product_id"] is None
    assert order["items"][0]["description"] == "Servicio especial"


async def test_create_order_with_catalog_item_auto_resolves_tier_price_when_unit_price_omitted(
    client: AsyncClient,
):
    """SPEC.md E2E criterion 6, the auto-resolve half: 12 units should hit
    the 10+ tier price, not the base price, when the operator doesn't
    override it."""
    headers, customer, cash, transfer, product = await _setup(
        client, business_name="Pedidos K", email="pedidosK@example.com"
    )
    await _give_customer_coordinates(client, headers, customer["id"])
    await client.put(
        f"/api/v1/products/{product['id']}/price-tiers",
        json=[{"min_quantity": 10, "unit_price": 2500}],
        headers=headers,
    )

    response = await client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 12}],
            "payment_method_id": transfer["id"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["items"][0]["unit_price"] == 2500
    assert order["amount"] == 2500 * 12


async def test_create_order_with_catalog_item_honors_operator_price_override(client: AsyncClient):
    """SPEC.md E2E criterion 6, the override half: "el operador puede
    sobreescribirlo" — a client-supplied unit_price alongside product_id
    must win over the auto-resolved tier price."""
    headers, customer, cash, transfer, product = await _setup(
        client, business_name="Pedidos L", email="pedidosL@example.com"
    )
    await _give_customer_coordinates(client, headers, customer["id"])
    await client.put(
        f"/api/v1/products/{product['id']}/price-tiers",
        json=[{"min_quantity": 10, "unit_price": 2500}],
        headers=headers,
    )

    response = await client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 12, "unit_price": 2000}],
            "payment_method_id": transfer["id"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["items"][0]["unit_price"] == 2000  # override, not the 2500 tier price
    assert order["amount"] == 2000 * 12


async def test_create_order_rejects_ambiguous_item_shape(client: AsyncClient):
    headers, customer, cash, transfer, product = await _setup(
        client, business_name="Pedidos D", email="pedidosD@example.com"
    )
    response = await client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "description": "no deberia ir", "quantity": 1}],
            "payment_method_id": transfer["id"],
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_create_order_rejects_ambiguous_customer_source(client: AsyncClient):
    headers, customer, cash, transfer, product = await _setup(
        client, business_name="Pedidos E", email="pedidosE@example.com"
    )
    response = await client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer["id"],
            "new_customer": {"phone": "+56933334444", "name": "Otro", "address": "Calle 2"},
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method_id": transfer["id"],
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_create_order_requires_cash_amount_when_payment_method_requires_change(
    client: AsyncClient,
):
    headers, customer, cash, transfer, product = await _setup(
        client, business_name="Pedidos F", email="pedidosF@example.com"
    )
    await _give_customer_coordinates(client, headers, customer["id"])

    response = await client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method_id": cash["id"],
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "cash_amount_required"


async def test_create_order_rejects_insufficient_cash_amount(client: AsyncClient):
    headers, customer, cash, transfer, product = await _setup(
        client, business_name="Pedidos G", email="pedidosG@example.com"
    )
    await _give_customer_coordinates(client, headers, customer["id"])

    response = await client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method_id": cash["id"],
            "cash_amount_given": 1000,
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "insufficient_cash_amount"


async def test_orders_are_tenant_isolated(client: AsyncClient):
    headers_a, customer_a, cash_a, transfer_a, product_a = await _setup(
        client, business_name="Pedidos H", email="pedidosH@example.com"
    )
    headers_b, customer_b, cash_b, transfer_b, product_b = await _setup(
        client, business_name="Pedidos I", email="pedidosI@example.com"
    )
    await _give_customer_coordinates(client, headers_b, customer_b["id"])

    order_b = (
        await client.post(
            "/api/v1/orders",
            json={
                "customer_id": customer_b["id"],
                "items": [{"product_id": product_b["id"], "quantity": 1}],
                "payment_method_id": transfer_b["id"],
            },
            headers=headers_b,
        )
    ).json()

    get_response = await client.get(f"/api/v1/orders/{order_b['id']}", headers=headers_a)
    assert get_response.status_code == 404


async def test_driver_role_is_rejected_on_order_create_and_assign(client: AsyncClient, db_session):
    headers, customer, cash, transfer, product = await _setup(
        client, business_name="Pedidos Driver", email="pedidosdriver@example.com"
    )
    me = await _whoami(client, headers["Authorization"].removeprefix("Bearer "))
    driver = await create_user_in_business(
        db_session,
        business_id=me["business_id"],
        role=UserRole.driver,
        email="driver-pedidos@example.com",
    )
    driver_token = create_access_token(driver.id, driver.business_id, UserRole.driver.value)

    create_response = await client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method_id": transfer["id"],
        },
        headers=_auth(driver_token),
    )
    assert create_response.status_code == 403
    assert create_response.json()["code"] == "forbidden_role"

    assign_response = await client.post(
        "/api/v1/orders/999999/assign", json={"driver_id": 1}, headers=_auth(driver_token)
    )
    assert assign_response.status_code == 403
    assert assign_response.json()["code"] == "forbidden_role"


async def test_list_orders_filters_by_status(client: AsyncClient):
    headers, customer, cash, transfer, product = await _setup(
        client, business_name="Pedidos J", email="pedidosJ@example.com"
    )
    await _give_customer_coordinates(client, headers, customer["id"])
    await client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method_id": transfer["id"],
        },
        headers=headers,
    )

    response = await client.get(
        "/api/v1/orders", params={"status": "pendiente"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1

    response = await client.get("/api/v1/orders", params={"status": "entregado"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_list_orders_filters_by_customer_id(client: AsyncClient):
    headers, customer_a, cash, transfer, product = await _setup(
        client, business_name="Pedidos M", email="pedidosM@example.com"
    )
    await _give_customer_coordinates(client, headers, customer_a["id"])
    customer_b = (
        await client.post(
            "/api/v1/customers",
            json={"phone": "+56933335555", "name": "Otro cliente", "address": "Calle 2"},
            headers=headers,
        )
    ).json()
    await _give_customer_coordinates(client, headers, customer_b["id"])

    for customer in (customer_a, customer_b):
        await client.post(
            "/api/v1/orders",
            json={
                "customer_id": customer["id"],
                "items": [{"product_id": product["id"], "quantity": 1}],
                "payment_method_id": transfer["id"],
            },
            headers=headers,
        )

    response = await client.get(
        "/api/v1/orders", params={"customer_id": customer_a["id"]}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["customer_id"] == customer_a["id"]
