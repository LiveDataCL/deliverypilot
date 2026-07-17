from pydantic import BaseModel

from app.models.enums import DriverStatus


class DriverOut(BaseModel):
    """Read-only — Driver CRUD (create/update/toggle online-offline) belongs
    to the Personal checkpoint, not this one. This exists only to feed the
    driver picker on the order-assignment action."""

    id: int
    business_id: int
    user_id: int
    vehicle_type: str
    status: DriverStatus

    model_config = {"from_attributes": True}
