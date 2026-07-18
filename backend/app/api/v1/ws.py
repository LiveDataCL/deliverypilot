"""WebSocket routes for the realtime driver-position/dispatch-event channel
(SPEC.md §5, Fase 1). Not under the /api/v1 prefix -- the spec's own route
literals are /ws/driver/{token} and /ws/dispatch/{token}.

Auth: the existing JWT access token, passed as the {token} path segment --
browsers' native WebSocket API can't set an Authorization header, so it has
to travel in the URL. Same signed-token-in-a-URL precedent as
tracking_token/invite links, not a new token type.

No Flutter driver app exists yet -- /ws/driver/{token} is exercised in tests
via a synthetic WebSocket test client sending simulated GPS pings, same
"test the contract, not the client" approach used for prefill/invite flows.
"""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from app.core.security import decode_token
from app.core.ws_manager import manager
from app.db.base import async_session_factory
from app.db.tenant import TenantContext, set_tenant_session
from app.models.driver import Driver
from app.models.enums import UserRole
from app.models.location_ping import LocationPing
from app.services import auth_service

router = APIRouter()

_DISPATCHER_ROLES = (UserRole.business_owner.value, UserRole.dispatcher.value)

# Throttle: only one location_pings row written per driver per this many
# seconds, even if pings arrive more often (Flutter checklist: 10s while
# moving / 60s stopped). Every ping still updates the in-memory position and
# broadcasts immediately regardless of this throttle -- only the DB write
# (location_pings history) is throttled, per SPEC.md §5's literal wording
# ("persiste en location_pings cada 60s").
_PING_PERSIST_INTERVAL_SECONDS = 60


class DriverPingIn(BaseModel):
    lat: Decimal
    lng: Decimal
    speed: Decimal | None = None
    battery: int | None = Field(default=None, ge=0, le=100)


async def _authenticate(token: str) -> TenantContext | None:
    try:
        payload = decode_token(token)
    except ValueError:
        return None
    if payload.token_type != "access":
        return None
    async with async_session_factory() as db:
        await set_tenant_session(db, payload.business_id)
        user = await auth_service.get_active_user(
            db, user_id=payload.user_id, business_id=payload.business_id
        )
        if user is None:
            return None
        return TenantContext(business_id=user.business_id, user_id=user.id, role=user.role.value)


@router.websocket("/ws/dispatch/{token}")
async def ws_dispatch(websocket: WebSocket, token: str) -> None:
    ctx = await _authenticate(token)
    if ctx is None or ctx.role not in _DISPATCHER_ROLES:
        await websocket.close(code=4401)
        return

    await manager.connect_dispatch(ctx.business_id, websocket)
    try:
        while True:
            # Dispatch clients are listen-only from this channel's point of
            # view -- this just blocks until the client disconnects. No
            # incoming message is ever acted on here.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_dispatch(ctx.business_id, websocket)


@router.websocket("/ws/driver/{token}")
async def ws_driver(websocket: WebSocket, token: str) -> None:
    ctx = await _authenticate(token)
    if ctx is None or ctx.role != UserRole.driver.value:
        await websocket.close(code=4401)
        return

    async with async_session_factory() as db:
        await set_tenant_session(db, ctx.business_id)
        driver_id = await db.scalar(
            select(Driver.id).where(Driver.business_id == ctx.business_id, Driver.user_id == ctx.user_id)
        )
    if driver_id is None:
        # A user with role=driver but no linked Driver row -- shouldn't
        # happen via the real staff-creation flow, but the socket has no
        # business accepting pings it can't attribute to a driver.
        await websocket.close(code=4401)
        return

    await websocket.accept()
    last_persisted_at: datetime | None = None
    try:
        while True:
            raw = await websocket.receive_json()
            try:
                ping = DriverPingIn.model_validate(raw)
            except ValidationError:
                # Malformed single ping -- drop it, keep the connection.
                continue

            now = datetime.now(timezone.utc)
            position = {
                "driver_id": driver_id,
                "lat": float(ping.lat),
                "lng": float(ping.lng),
                "speed": float(ping.speed) if ping.speed is not None else None,
                "battery": ping.battery,
                "recorded_at": now.isoformat(),
            }
            manager.update_driver_position(ctx.business_id, driver_id, position)
            await manager.broadcast(ctx.business_id, {"type": "driver_position", **position})

            should_persist = (
                last_persisted_at is None
                or (now - last_persisted_at).total_seconds() >= _PING_PERSIST_INTERVAL_SECONDS
            )
            if should_persist:
                async with async_session_factory() as persist_db:
                    await set_tenant_session(persist_db, ctx.business_id)
                    persist_db.add(
                        LocationPing(
                            business_id=ctx.business_id,
                            driver_id=driver_id,
                            lat=ping.lat,
                            lng=ping.lng,
                            speed=ping.speed,
                            battery=ping.battery,
                        )
                    )
                    driver = await persist_db.get(Driver, driver_id)
                    if driver is not None:
                        driver.last_lat = ping.lat
                        driver.last_lng = ping.lng
                        driver.last_seen_at = now
                    await persist_db.commit()
                last_persisted_at = now
    except WebSocketDisconnect:
        pass
