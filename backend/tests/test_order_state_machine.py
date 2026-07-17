import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.enums import UserRole
from tests.conftest import create_driver_in_business, register_business

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _whoami(client: AsyncClient, access_token: str) -> dict:
    response = await client.get("/api/v1/auth/me", headers=_auth(access_token))
    assert response.status_code == 200
    return response.json()


async def _setup_order(client: AsyncClient, *, business_name: str, email: str):
    tokens = await register_business(client, business_name=business_name, email=email)
    headers = _auth(tokens["access_token"])
    me = await _whoami(client, tokens["access_token"])
    customer = (
        await client.post(
            "/api/v1/customers",
            json={"phone": "+56911112222", "name": "Cliente", "address": "Calle 1"},
            headers=headers,
        )
    ).json()
    await client.patch(
        f"/api/v1/customers/{customer['id']}", json={"lat": "-33.45", "lng": "-70.65"}, headers=headers
    )
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
    order = (
        await client.post(
            "/api/v1/orders",
            json={
                "customer_id": customer["id"],
                "items": [{"product_id": product["id"], "quantity": 1}],
                "payment_method_id": transfer["id"],
            },
            headers=headers,
        )
    ).json()
    return headers, me, order


async def test_dispatcher_can_assign_a_pendiente_order_to_a_driver(client: AsyncClient, db_session):
    headers, me, order = await _setup_order(
        client, business_name="StateMachine A", email="statemachineA@example.com"
    )
    driver = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverA@example.com"
    )

    response = await client.post(
        f"/api/v1/orders/{order['id']}/assign", json={"driver_id": driver.id}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "asignado"
    assert body["driver_id"] == driver.id
    assert body["assigned_at"] is not None


async def test_assign_driver_rejects_a_cross_tenant_driver_id(client: AsyncClient, db_session):
    headers, me, order = await _setup_order(
        client, business_name="StateMachine B", email="statemachineB@example.com"
    )
    _, other_me, _ = await _setup_order(
        client, business_name="StateMachine B Other", email="statemachineBother@example.com"
    )
    other_driver = await create_driver_in_business(
        db_session, business_id=other_me["business_id"], email="driverB-other@example.com"
    )

    response = await client.post(
        f"/api/v1/orders/{order['id']}/assign", json={"driver_id": other_driver.id}, headers=headers
    )
    assert response.status_code == 404
    assert response.json()["code"] == "driver_not_found"


async def test_assign_driver_fails_if_order_is_not_pendiente(client: AsyncClient, db_session):
    headers, me, order = await _setup_order(
        client, business_name="StateMachine C", email="statemachineC@example.com"
    )
    driver = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverC@example.com"
    )
    await client.post(f"/api/v1/orders/{order['id']}/assign", json={"driver_id": driver.id}, headers=headers)

    second_response = await client.post(
        f"/api/v1/orders/{order['id']}/assign", json={"driver_id": driver.id}, headers=headers
    )
    assert second_response.status_code == 400
    assert second_response.json()["code"] == "invalid_transition"


async def test_dispatcher_can_cancel_a_pendiente_order(client: AsyncClient):
    headers, me, order = await _setup_order(
        client, business_name="StateMachine D", email="statemachineD@example.com"
    )
    response = await client.patch(
        f"/api/v1/orders/{order['id']}/status", json={"status": "cancelado"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelado"


async def test_driver_can_advance_their_own_assigned_order_through_full_lifecycle(
    client: AsyncClient, db_session
):
    headers, me, order = await _setup_order(
        client, business_name="StateMachine E", email="statemachineE@example.com"
    )
    driver = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverE@example.com"
    )
    await client.post(f"/api/v1/orders/{order['id']}/assign", json={"driver_id": driver.id}, headers=headers)
    driver_token = create_access_token(driver.user_id, driver.business_id, UserRole.driver.value)
    driver_headers = _auth(driver_token)

    for status_value, timestamp_field in [
        ("aceptado", "accepted_at"),
        ("recogido", "picked_up_at"),
        ("en_ruta", None),
        ("entregado", "delivered_at"),
    ]:
        response = await client.patch(
            f"/api/v1/orders/{order['id']}/status", json={"status": status_value}, headers=driver_headers
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == status_value
        if timestamp_field is not None:
            assert body[timestamp_field] is not None


async def test_second_driver_is_rejected_from_advancing_a_different_drivers_order(
    client: AsyncClient, db_session
):
    headers, me, order = await _setup_order(
        client, business_name="StateMachine F", email="statemachineF@example.com"
    )
    driver_1 = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverF-1@example.com"
    )
    driver_2 = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverF-2@example.com"
    )
    await client.post(
        f"/api/v1/orders/{order['id']}/assign", json={"driver_id": driver_1.id}, headers=headers
    )
    driver_2_token = create_access_token(driver_2.user_id, driver_2.business_id, UserRole.driver.value)

    response = await client.patch(
        f"/api/v1/orders/{order['id']}/status",
        json={"status": "aceptado"},
        headers=_auth(driver_2_token),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden_transition"


async def test_dispatcher_is_rejected_from_a_driver_only_transition(client: AsyncClient, db_session):
    headers, me, order = await _setup_order(
        client, business_name="StateMachine G", email="statemachineG@example.com"
    )
    driver = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverG@example.com"
    )
    await client.post(f"/api/v1/orders/{order['id']}/assign", json={"driver_id": driver.id}, headers=headers)

    response = await client.patch(
        f"/api/v1/orders/{order['id']}/status", json={"status": "aceptado"}, headers=headers
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden_transition"


async def test_driver_is_rejected_from_cancelling_an_order(client: AsyncClient, db_session):
    headers, me, order = await _setup_order(
        client, business_name="StateMachine H", email="statemachineH@example.com"
    )
    driver = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverH@example.com"
    )
    await client.post(f"/api/v1/orders/{order['id']}/assign", json={"driver_id": driver.id}, headers=headers)
    driver_token = create_access_token(driver.user_id, driver.business_id, UserRole.driver.value)

    response = await client.patch(
        f"/api/v1/orders/{order['id']}/status",
        json={"status": "cancelado"},
        headers=_auth(driver_token),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden_transition"


async def test_invalid_transition_is_rejected(client: AsyncClient):
    headers, me, order = await _setup_order(
        client, business_name="StateMachine I", email="statemachineI@example.com"
    )
    response = await client.patch(
        f"/api/v1/orders/{order['id']}/status", json={"status": "entregado"}, headers=headers
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_transition"


async def test_entregado_transition_fires_recalculate_customer_defaults(client: AsyncClient, db_session):
    headers, me, order = await _setup_order(
        client, business_name="StateMachine J", email="statemachineJ@example.com"
    )
    driver = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverJ@example.com"
    )
    await client.post(f"/api/v1/orders/{order['id']}/assign", json={"driver_id": driver.id}, headers=headers)
    driver_token = create_access_token(driver.user_id, driver.business_id, UserRole.driver.value)
    driver_headers = _auth(driver_token)

    for status_value in ["aceptado", "recogido", "en_ruta", "entregado"]:
        response = await client.patch(
            f"/api/v1/orders/{order['id']}/status", json={"status": status_value}, headers=driver_headers
        )
        assert response.status_code == 200, response.text

    prefill = await client.get(f"/api/v1/customers/{order['customer_id']}/prefill", headers=headers)
    assert prefill.status_code == 200
    body = prefill.json()
    # Only 1 delivered order so far -> "last_order" path, but the mere fact
    # that recalculate ran is what customer_defaults/order_frequency_days
    # would reflect with >=3 orders; here we confirm the wiring fired at all
    # by checking last_order_at got set (only recalculate_customer_defaults
    # or a delivered-order-aware path would do that).
    customer = (await client.get(f"/api/v1/customers/{order['customer_id']}", headers=headers)).json()
    assert customer["last_order_at"] is not None
