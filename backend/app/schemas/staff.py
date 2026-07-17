from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class StaffCreate(BaseModel):
    email: EmailStr
    phone: str | None = None
    role: Literal["dispatcher", "driver"]
    vehicle_type: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _vehicle_type_matches_role(self) -> "StaffCreate":
        if self.role == "driver" and not self.vehicle_type:
            raise ValueError("vehicle_type es requerido para repartidores")
        if self.role == "dispatcher" and self.vehicle_type is not None:
            raise ValueError("vehicle_type no aplica a despachadores")
        return self


class StaffOut(BaseModel):
    id: int
    business_id: int
    role: str
    email: str
    phone: str | None
    is_active: bool
    invite_accepted_at: datetime | None
    created_at: datetime
    # Only present for role="driver".
    vehicle_type: str | None = None
    driver_status: str | None = None

    model_config = {"from_attributes": True}


class StaffCreateResponse(BaseModel):
    staff: StaffOut
    # Raw token only — the frontend builds the full shareable link itself
    # (`${origin}/aceptar-invitacion/${token}`), so the backend never needs
    # to know its own frontend's public URL.
    invite_token: str


class ResetPasswordResponse(BaseModel):
    invite_token: str


class AcceptInviteIn(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=100)

    @field_validator("new_password")
    @classmethod
    def _password_must_fit_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contrasena no puede superar los 72 bytes")
        return value
