from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import DriverStatus


class DriverOut(BaseModel):
    """Read-only — Driver CRUD (create/update/toggle online-offline) belongs
    to the Personal checkpoint, not this one. Originally built to feed the
    driver picker on the order-assignment action; last_lat/last_lng/
    last_seen_at were added for the live map's initial render — the
    in-process position cache (app/core/ws_manager.py) only knows about
    pings received since this backend process last started, so a driver's
    last-known position from before a restart/redeploy has to come from
    here instead."""

    id: int
    business_id: int
    user_id: int
    vehicle_type: str
    status: DriverStatus
    last_lat: Decimal | None
    last_lng: Decimal | None
    last_seen_at: datetime | None

    model_config = {"from_attributes": True}
