"""Integration tests for the /ws/driver/{token} and /ws/dispatch/{token}
routes (app/api/v1/ws.py). Uses httpx-ws's aconnect_ws, which runs the ASGI
app inside the same event loop as the rest of this async test suite --
fastapi.testclient.TestClient's WS support was tried first and rejected: it
runs the app in a separate thread/event loop, which collides with this
project's shared async engine (see the "attached to a different loop"
RuntimeError from that spike, and docs/digital-debt.md's asyncpg entry for
the same general class of Windows/event-loop fragility).

No Flutter driver app exists yet -- every driver-side test here drives
/ws/driver/{token} with a synthetic ping payload, not a real device.
"""
import asyncio
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from httpx_ws import WebSocketDisconnect, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.tenant import set_tenant_session
from app.main import app
from app.models.driver import Driver
from app.models.location_ping import LocationPing
from tests.conftest import create_driver_in_business, register_business

pytestmark = pytest.mark.asyncio

_RECEIVE_TIMEOUT = 5


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _whoami(client: AsyncClient, access_token: str) -> dict:
    response = await client.get("/api/v1/auth/me", headers=_auth(access_token))
    assert response.status_code == 200
    return response.json()


def _ws_client() -> AsyncClient:
    # Default initial_receive_timeout is 1.0s -- too short for _authenticate's
    # real DB round-trip (set_tenant_session + get_active_user) on this
    # environment, causing spurious RuntimeErrors on otherwise-successful
    # connects. 10s gives real headroom without making a genuinely-hung
    # connection take forever to fail.
    transport = ASGIWebSocketTransport(app, initial_receive_timeout=10.0)
    return AsyncClient(transport=transport, base_url="http://test")


async def _setup_business(client: AsyncClient, *, business_name: str, email: str):
    tokens = await register_business(client, business_name=business_name, email=email)
    me = await _whoami(client, tokens["access_token"])
    return tokens["access_token"], me


async def test_ws_dispatch_rejects_an_invalid_token():
    async with _ws_client() as ws_client:
        with pytest.raises(WebSocketDisconnect):
            async with aconnect_ws("/ws/dispatch/not-a-real-token", ws_client):
                pass


async def test_ws_dispatch_rejects_a_driver_role(client: AsyncClient, db_session):
    access_token, me = await _setup_business(
        client, business_name="WS Dispatch Reject", email="wsdispatchreject@example.com"
    )
    driver = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverwsreject@example.com"
    )
    driver_token = create_access_token(driver.user_id, me["business_id"], "driver")

    async with _ws_client() as ws_client:
        with pytest.raises(WebSocketDisconnect):
            async with aconnect_ws(f"/ws/dispatch/{driver_token}", ws_client):
                pass


async def test_ws_driver_rejects_a_dispatcher_role(client: AsyncClient):
    access_token, me = await _setup_business(
        client, business_name="WS Driver Reject", email="wsdriverreject@example.com"
    )
    async with _ws_client() as ws_client:
        with pytest.raises(WebSocketDisconnect):
            async with aconnect_ws(f"/ws/driver/{access_token}", ws_client):
                pass


async def test_ws_driver_ping_broadcasts_live_to_a_connected_dispatch_socket(
    client: AsyncClient, db_session
):
    access_token, me = await _setup_business(
        client, business_name="WS Broadcast", email="wsbroadcast@example.com"
    )
    driver = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverwsbroadcast@example.com"
    )
    driver_token = create_access_token(driver.user_id, me["business_id"], "driver")

    async with _ws_client() as ws_client:
        async with aconnect_ws(f"/ws/dispatch/{access_token}", ws_client) as dispatch_ws:
            async with aconnect_ws(f"/ws/driver/{driver_token}", ws_client) as driver_ws:
                await driver_ws.send_json({"lat": -33.45, "lng": -70.65, "speed": 12.5, "battery": 80})

                event = await asyncio.wait_for(dispatch_ws.receive_json(), timeout=_RECEIVE_TIMEOUT)
                assert event["type"] == "driver_position"
                assert event["driver_id"] == driver.id
                assert event["lat"] == -33.45
                assert event["lng"] == -70.65
                assert event["speed"] == 12.5
                assert event["battery"] == 80


async def test_ws_dispatch_hydrates_a_new_connection_with_known_positions(
    client: AsyncClient, db_session
):
    """The in-memory position cache (ConnectionManager, not Redis -- see
    docs/digital-debt.md) must let a dispatch client that connects *after*
    a driver has already pinged still see that driver's last position,
    without waiting for the next ping."""
    access_token, me = await _setup_business(
        client, business_name="WS Hydrate", email="wshydrate@example.com"
    )
    driver = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverwshydrate@example.com"
    )
    driver_token = create_access_token(driver.user_id, me["business_id"], "driver")

    async with _ws_client() as ws_client:
        async with aconnect_ws(f"/ws/driver/{driver_token}", ws_client) as driver_ws:
            await driver_ws.send_json({"lat": -33.1, "lng": -70.1})
            # No dispatch socket connected yet -- give the server a beat to
            # process the ping before the (later) dispatch connection races it.
            await asyncio.sleep(0.2)

            async with aconnect_ws(f"/ws/dispatch/{access_token}", ws_client) as dispatch_ws:
                snapshot = await asyncio.wait_for(dispatch_ws.receive_json(), timeout=_RECEIVE_TIMEOUT)
                assert snapshot["type"] == "positions_snapshot"
                assert snapshot["positions"] == [
                    {
                        "driver_id": driver.id,
                        "lat": -33.1,
                        "lng": -70.1,
                        "speed": None,
                        "battery": None,
                        "recorded_at": snapshot["positions"][0]["recorded_at"],
                    }
                ]


async def test_ws_driver_position_does_not_leak_to_a_different_business(client: AsyncClient, db_session):
    _access_token_a, me_a = await _setup_business(
        client, business_name="WS Isolation A", email="wsisolationA@example.com"
    )
    access_token_b, me_b = await _setup_business(
        client, business_name="WS Isolation B", email="wsisolationB@example.com"
    )
    driver_a = await create_driver_in_business(
        db_session, business_id=me_a["business_id"], email="driverwsisolationA@example.com"
    )
    driver_a_token = create_access_token(driver_a.user_id, me_a["business_id"], "driver")

    async with _ws_client() as ws_client:
        async with aconnect_ws(f"/ws/dispatch/{access_token_b}", ws_client) as dispatch_b_ws:
            async with aconnect_ws(f"/ws/driver/{driver_a_token}", ws_client) as driver_a_ws:
                await driver_a_ws.send_json({"lat": -33.45, "lng": -70.65})
                # business B's dispatch socket must never receive business A's
                # ping -- assert by racing a short timeout instead of a
                # positive "nothing arrived forever" wait.
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(dispatch_b_ws.receive_json(), timeout=1)


async def test_ws_driver_ping_persists_a_location_ping_and_updates_driver_last_seen(
    client: AsyncClient, db_session
):
    access_token, me = await _setup_business(
        client, business_name="WS Persist", email="wspersist@example.com"
    )
    driver = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverwspersist@example.com"
    )
    driver_token = create_access_token(driver.user_id, me["business_id"], "driver")

    before = datetime.now(timezone.utc)
    async with _ws_client() as ws_client:
        async with aconnect_ws(f"/ws/driver/{driver_token}", ws_client) as driver_ws:
            await driver_ws.send_json({"lat": -33.45, "lng": -70.65, "battery": 55})
            await asyncio.sleep(0.3)  # let the server's persist branch complete

    await set_tenant_session(db_session, me["business_id"])
    pings = list(
        (
            await db_session.scalars(
                select(LocationPing).where(LocationPing.driver_id == driver.id)
            )
        ).all()
    )
    assert len(pings) == 1
    assert pings[0].battery == 55

    # populate_existing=True: db_session already has this exact Driver row in
    # its identity map from create_driver_in_business earlier in this test --
    # without it, .get() would silently return that stale cached copy
    # (last_lat=None) instead of re-reading the row the WS handler's
    # separate session actually committed the update to.
    refreshed_driver = await db_session.get(Driver, driver.id, populate_existing=True)
    assert refreshed_driver.last_lat == pings[0].lat
    assert refreshed_driver.last_seen_at is not None
    assert refreshed_driver.last_seen_at >= before


async def test_ws_driver_two_quick_pings_only_persist_one_location_ping_row(
    client: AsyncClient, db_session
):
    """The 60s persistence throttle (SPEC.md §5) -- both pings still update
    the live broadcast/position cache, but only the first should hit
    location_pings within the same throttle window."""
    access_token, me = await _setup_business(
        client, business_name="WS Throttle", email="wsthrottle@example.com"
    )
    driver = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverwsthrottle@example.com"
    )
    driver_token = create_access_token(driver.user_id, me["business_id"], "driver")

    async with _ws_client() as ws_client:
        async with aconnect_ws(f"/ws/driver/{driver_token}", ws_client) as driver_ws:
            await driver_ws.send_json({"lat": -33.1, "lng": -70.1})
            await asyncio.sleep(0.2)
            await driver_ws.send_json({"lat": -33.2, "lng": -70.2})
            await asyncio.sleep(0.2)

    await set_tenant_session(db_session, me["business_id"])
    pings = list(
        (
            await db_session.scalars(
                select(LocationPing).where(LocationPing.driver_id == driver.id)
            )
        ).all()
    )
    assert len(pings) == 1


async def test_assign_driver_broadcasts_order_status_changed(client: AsyncClient, db_session):
    access_token, me = await _setup_business(
        client, business_name="WS Assign Broadcast", email="wsassignbroadcast@example.com"
    )
    headers = _auth(access_token)
    driver = await create_driver_in_business(
        db_session, business_id=me["business_id"], email="driverwsassign@example.com"
    )
    customer = (
        await client.post(
            "/api/v1/customers",
            json={"phone": "+56911119999", "name": "Cliente WS", "address": "Calle WS 1"},
            headers=headers,
        )
    ).json()
    await client.patch(
        f"/api/v1/customers/{customer['id']}", json={"lat": "-33.45", "lng": "-70.65"}, headers=headers
    )
    payment_method = (
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

    async with _ws_client() as ws_client:
        async with aconnect_ws(f"/ws/dispatch/{access_token}", ws_client) as dispatch_ws:
            order_response = await client.post(
                "/api/v1/orders",
                json={
                    "customer_id": customer["id"],
                    "items": [{"product_id": product["id"], "quantity": 1}],
                    "payment_method_id": payment_method["id"],
                },
                headers=headers,
            )
            assert order_response.status_code == 201, order_response.text
            order = order_response.json()

            created_event = await asyncio.wait_for(dispatch_ws.receive_json(), timeout=_RECEIVE_TIMEOUT)
            assert created_event == {"type": "order_created", "order_id": order["id"], "status": "pendiente"}

            assign_response = await client.post(
                f"/api/v1/orders/{order['id']}/assign",
                json={"driver_id": driver.id},
                headers=headers,
            )
            # FCM is unconfigured in every test env -- the push is a no-op,
            # but the assignment itself must still succeed (send_push/
            # broadcast failures must never break the business action).
            assert assign_response.status_code == 200, assign_response.text

            assigned_event = await asyncio.wait_for(dispatch_ws.receive_json(), timeout=_RECEIVE_TIMEOUT)
            assert assigned_event == {
                "type": "order_status_changed",
                "order_id": order["id"],
                "status": "asignado",
                "driver_id": driver.id,
            }


async def test_transition_order_status_broadcasts_order_status_changed(client: AsyncClient):
    access_token, me = await _setup_business(
        client, business_name="WS Transition Broadcast", email="wstransitionbroadcast@example.com"
    )
    headers = _auth(access_token)
    customer = (
        await client.post(
            "/api/v1/customers",
            json={"phone": "+56911118888", "name": "Cliente WS2", "address": "Calle WS 2"},
            headers=headers,
        )
    ).json()
    await client.patch(
        f"/api/v1/customers/{customer['id']}", json={"lat": "-33.45", "lng": "-70.65"}, headers=headers
    )
    payment_method = (
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
                "payment_method_id": payment_method["id"],
            },
            headers=headers,
        )
    ).json()

    async with _ws_client() as ws_client:
        async with aconnect_ws(f"/ws/dispatch/{access_token}", ws_client) as dispatch_ws:
            cancel_response = await client.patch(
                f"/api/v1/orders/{order['id']}/status", json={"status": "cancelado"}, headers=headers
            )
            assert cancel_response.status_code == 200, cancel_response.text

            event = await asyncio.wait_for(dispatch_ws.receive_json(), timeout=_RECEIVE_TIMEOUT)
            assert event == {
                "type": "order_status_changed",
                "order_id": order["id"],
                "status": "cancelado",
            }
