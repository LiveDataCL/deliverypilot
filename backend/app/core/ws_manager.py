"""In-process WebSocket connection manager for the dispatch/live-map realtime
channel. See docs/digital-debt.md ("Redis pub/sub deferred in favor of
in-process WebSocket broadcast") for why this is in-memory rather than Redis
pub/sub at the current single-backend-instance scale, and for the exact
point at which this needs to be swapped out.
"""
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Holds every business's dispatch WebSocket connections and each
    driver's last-known position, both purely in memory -- this process is
    the only source of truth. Resets on restart/redeploy; see the
    digital-debt entry for why that's an accepted tradeoff at this scale."""

    def __init__(self) -> None:
        self._dispatch_connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._driver_positions: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)

    async def connect_dispatch(self, business_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._dispatch_connections[business_id].add(websocket)
        positions = list(self._driver_positions[business_id].values())
        if positions:
            await websocket.send_json({"type": "positions_snapshot", "positions": positions})

    def disconnect_dispatch(self, business_id: int, websocket: WebSocket) -> None:
        connections = self._dispatch_connections.get(business_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            del self._dispatch_connections[business_id]

    async def broadcast(self, business_id: int, event: dict[str, Any]) -> None:
        """Fire-and-forget to every dispatch socket currently connected for
        this business. A send failure on one socket (client gone but not yet
        disconnected) must not stop delivery to the others -- dead sockets
        are collected and dropped after the loop instead of failing the
        whole broadcast."""
        connections = list(self._dispatch_connections.get(business_id, ()))
        dead: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(event)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect_dispatch(business_id, websocket)

    def update_driver_position(self, business_id: int, driver_id: int, position: dict[str, Any]) -> None:
        self._driver_positions[business_id][driver_id] = position


# Process-wide singleton -- correct for a single backend instance (see the
# digital-debt entry above). One FastAPI app, one asyncio event loop: dict
# mutations here never straddle an `await`, so no lock is needed.
manager = ConnectionManager()
