from pydantic import BaseModel, Field

from app.models.enums import PaymentMethodType


class PaymentMethodCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: PaymentMethodType
    requires_change: bool = False
    active: bool = True
    sort_order: int = 0


class PaymentMethodUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: PaymentMethodType | None = None
    requires_change: bool | None = None
    active: bool | None = None
    sort_order: int | None = None


class PaymentMethodOut(BaseModel):
    id: int
    business_id: int
    name: str
    type: PaymentMethodType
    requires_change: bool
    active: bool
    sort_order: int

    model_config = {"from_attributes": True}
