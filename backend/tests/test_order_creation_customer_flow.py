from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import register_business

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient, *, business_name: str, email: str):
    tokens = await register_business(client, business_name=business_name, email=email)
    headers = _auth(tokens["access_token"])
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
    return headers, transfer, product


def _mock_geocode(monkeypatch, *, result):
    calls = []

    async def fake_geocode_address(address: str):
        calls.append(address)
        return result

    monkeypatch.setattr("app.services.order_service.geocode_address", fake_geocode_address)
    return calls


async def test_create_order_with_new_customer_geocodes_and_creates_customer(
    client: AsyncClient, monkeypatch
):
    headers, transfer, product = await _setup(
        client, business_name="OrderCust A", email="ordercustA@example.com"
    )
    calls = _mock_geocode(monkeypatch, result=(Decimal("-33.5"), Decimal("-70.6")))

    response = await client.post(
        "/api/v1/orders",
        json={
            "new_customer": {
                "phone": "+56911119999",
                "name": "Cliente Nuevo",
                "address": "Avenida Siempre Viva 742",
            },
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method_id": transfer["id"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["customer_id"] is not None
    assert Decimal(order["delivery_lat"]) == Decimal("-33.5")
    assert Decimal(order["delivery_lng"]) == Decimal("-70.6")
    assert calls == ["Avenida Siempre Viva 742"]

    customers = (await client.get("/api/v1/customers", headers=headers)).json()["items"]
    assert any(c["id"] == order["customer_id"] and c["phone"] == "+56911119999" for c in customers)


async def test_create_order_reuses_existing_customer_when_phone_already_exists(
    client: AsyncClient, monkeypatch
):
    headers, transfer, product = await _setup(
        client, business_name="OrderCust B", email="ordercustB@example.com"
    )
    existing = (
        await client.post(
            "/api/v1/customers",
            json={"phone": "+56922223333", "name": "Ya existe", "address": "Calle Real 1"},
            headers=headers,
        )
    ).json()
    await client.patch(
        f"/api/v1/customers/{existing['id']}",
        json={"lat": "-33.1", "lng": "-70.1"},
        headers=headers,
    )
    calls = _mock_geocode(monkeypatch, result=None)

    response = await client.post(
        "/api/v1/orders",
        json={
            "new_customer": {
                "phone": "+56922223333",
                "name": "Nombre distinto en el formulario",
                "address": "Otra direccion",
            },
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method_id": transfer["id"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    order = response.json()
    # Reused the existing customer (same id, same stored name/address/coords)
    # rather than creating a second row or erroring on the duplicate phone.
    assert order["customer_id"] == existing["id"]
    assert order["customer_name"] == "Ya existe"
    assert Decimal(order["delivery_lat"]) == Decimal("-33.1")
    assert calls == []  # already had coordinates -- geocoding never called

    customers = (await client.get("/api/v1/customers", headers=headers)).json()["items"]
    assert len([c for c in customers if c["phone"] == "+56922223333"]) == 1


async def test_create_order_with_manual_override_skips_geocoding(client: AsyncClient, monkeypatch):
    headers, transfer, product = await _setup(
        client, business_name="OrderCust C", email="ordercustC@example.com"
    )
    calls = _mock_geocode(monkeypatch, result=(Decimal("0"), Decimal("0")))

    response = await client.post(
        "/api/v1/orders",
        json={
            "new_customer": {
                "phone": "+56933334444",
                "name": "Con coordenadas manuales",
                "address": "Direccion cualquiera",
                "lat": "-33.9",
                "lng": "-70.9",
            },
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method_id": transfer["id"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    order = response.json()
    assert Decimal(order["delivery_lat"]) == Decimal("-33.9")
    assert Decimal(order["delivery_lng"]) == Decimal("-70.9")
    assert calls == []  # manual override provided -- geocoding must not be called


async def test_create_order_geocoding_failure_returns_a_clear_actionable_error(
    client: AsyncClient, monkeypatch
):
    headers, transfer, product = await _setup(
        client, business_name="OrderCust D", email="ordercustD@example.com"
    )
    _mock_geocode(monkeypatch, result=None)

    response = await client.post(
        "/api/v1/orders",
        json={
            "new_customer": {
                "phone": "+56944445555",
                "name": "Direccion inubicable",
                "address": "Direccion que no existe en ningun lado",
            },
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method_id": transfer["id"],
        },
        headers=headers,
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "geocoding_failed"
    # Must clearly tell the operator both that it failed AND that they can
    # retry or enter coordinates manually -- not just "geocoding failed".
    assert "intenta nuevamente" in body["detail"].lower()
    assert "coordenadas manualmente" in body["detail"].lower()


async def test_create_order_geocodes_and_caches_for_existing_customer_missing_coordinates(
    client: AsyncClient, monkeypatch
):
    headers, transfer, product = await _setup(
        client, business_name="OrderCust E", email="ordercustE@example.com"
    )
    # Created via the plain Clientes CRUD, which never requires lat/lng.
    existing = (
        await client.post(
            "/api/v1/customers",
            json={"phone": "+56955556666", "name": "Sin coordenadas", "address": "Calle sin geocodificar"},
            headers=headers,
        )
    ).json()
    assert existing["lat"] is None

    calls = _mock_geocode(monkeypatch, result=(Decimal("-33.7"), Decimal("-70.7")))

    response = await client.post(
        "/api/v1/orders",
        json={
            "customer_id": existing["id"],
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method_id": transfer["id"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert calls == ["Calle sin geocodificar"]

    updated = (await client.get(f"/api/v1/customers/{existing['id']}", headers=headers)).json()
    assert Decimal(updated["lat"]) == Decimal("-33.7")
    assert Decimal(updated["lng"]) == Decimal("-70.7")
