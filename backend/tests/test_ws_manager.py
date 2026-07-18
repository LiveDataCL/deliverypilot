"""Unit tests for app/core/ws_manager.py's ConnectionManager -- pure
in-memory logic, no real socket/DB needed, so these use a minimal fake
WebSocket double (same "lightweight fake for an external-ish boundary"
approach as httpx.MockTransport in test_geocoding_service.py) rather than a
real network connection."""
import pytest

from app.core.ws_manager import ConnectionManager

pytestmark = pytest.mark.asyncio


class FakeWebSocket:
    def __init__(self, *, fail_on_send: bool = False):
        self.accepted = False
        self.sent: list[dict] = []
        self._fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict) -> None:
        if self._fail_on_send:
            raise RuntimeError("simulated dead socket")
        self.sent.append(data)


async def test_broadcast_sends_to_every_connected_socket_for_that_business():
    manager = ConnectionManager()
    ws1, ws2 = FakeWebSocket(), FakeWebSocket()
    await manager.connect_dispatch(1, ws1)
    await manager.connect_dispatch(1, ws2)

    await manager.broadcast(1, {"type": "order_created", "order_id": 42})

    assert ws1.sent == [{"type": "order_created", "order_id": 42}]
    assert ws2.sent == [{"type": "order_created", "order_id": 42}]


async def test_broadcast_does_not_leak_to_a_different_business():
    manager = ConnectionManager()
    ws_a, ws_b = FakeWebSocket(), FakeWebSocket()
    await manager.connect_dispatch(1, ws_a)
    await manager.connect_dispatch(2, ws_b)

    await manager.broadcast(1, {"type": "order_created", "order_id": 42})

    assert ws_a.sent == [{"type": "order_created", "order_id": 42}]
    assert ws_b.sent == []


async def test_broadcast_with_no_connected_sockets_is_a_noop():
    manager = ConnectionManager()
    # Must not raise even though business_id 999 has never connected.
    await manager.broadcast(999, {"type": "order_created", "order_id": 1})


async def test_connect_dispatch_accepts_the_socket():
    manager = ConnectionManager()
    ws = FakeWebSocket()
    await manager.connect_dispatch(1, ws)
    assert ws.accepted is True


async def test_connect_dispatch_hydrates_a_new_connection_with_known_positions():
    manager = ConnectionManager()
    manager.update_driver_position(1, 7, {"driver_id": 7, "lat": -33.45, "lng": -70.65})

    ws = FakeWebSocket()
    await manager.connect_dispatch(1, ws)

    assert ws.sent == [
        {"type": "positions_snapshot", "positions": [{"driver_id": 7, "lat": -33.45, "lng": -70.65}]}
    ]


async def test_connect_dispatch_sends_nothing_extra_when_no_positions_are_known_yet():
    manager = ConnectionManager()
    ws = FakeWebSocket()
    await manager.connect_dispatch(1, ws)
    assert ws.sent == []


async def test_disconnect_removes_the_socket():
    manager = ConnectionManager()
    ws = FakeWebSocket()
    await manager.connect_dispatch(1, ws)
    manager.disconnect_dispatch(1, ws)

    await manager.broadcast(1, {"type": "order_created", "order_id": 1})
    assert ws.sent == []


async def test_disconnect_on_a_business_with_no_connections_does_not_raise():
    manager = ConnectionManager()
    ws = FakeWebSocket()
    # Never connected -- disconnect must be a safe no-op, not a KeyError.
    manager.disconnect_dispatch(999, ws)


async def test_broadcast_drops_a_dead_socket_without_failing_delivery_to_the_others():
    manager = ConnectionManager()
    dead, alive = FakeWebSocket(fail_on_send=True), FakeWebSocket()
    await manager.connect_dispatch(1, dead)
    await manager.connect_dispatch(1, alive)

    await manager.broadcast(1, {"type": "order_created", "order_id": 1})

    assert alive.sent == [{"type": "order_created", "order_id": 1}]
    # The dead socket must have been dropped from the connection set as a
    # side effect of the failed send -- not just skipped for this one call.
    assert dead not in manager._dispatch_connections[1]
    assert alive in manager._dispatch_connections[1]
