from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import OrderStatus

_PHONE_PATTERN = r"^\+56\d{9}$"


class NewCustomerIn(BaseModel):
    phone: str = Field(pattern=_PHONE_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=300)
    address_detail: str | None = Field(default=None, max_length=200)
    # Manual override if Nominatim can't resolve the address — delivery_lat/
    # delivery_lng are NOT NULL on orders (Fase 0 schema), so a geocoding
    # failure needs an escape hatch rather than silently leaving them unset.
    lat: Decimal | None = None
    lng: Decimal | None = None


class OrderItemIn(BaseModel):
    product_id: int | None = None
    description: str | None = Field(default=None, max_length=300)
    quantity: int = Field(gt=0)
    unit_price: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_product_or_adhoc(self) -> "OrderItemIn":
        if self.product_id is not None:
            if self.description is not None:
                raise ValueError(
                    "product_id items resolve name from the catalog; don't also send description"
                )
            # unit_price is optional here: absent -> auto-resolve via
            # resolve_unit_price's tier logic; present -> the operator's
            # manual override wins (SPEC.md E2E criterion 6: "el operador
            # puede sobreescribirlo").
        elif self.description is None or self.unit_price is None:
            raise ValueError("ad-hoc items (no product_id) require both description and unit_price")
        return self


class OrderCreate(BaseModel):
    customer_id: int | None = None
    new_customer: NewCustomerIn | None = None
    items: list[OrderItemIn] = Field(min_length=1)
    payment_method_id: int
    cash_amount_given: int | None = Field(default=None, ge=0)
    notes: str | None = None
    pickup_address: str | None = Field(default=None, max_length=300)
    pickup_lat: Decimal | None = None
    pickup_lng: Decimal | None = None

    @model_validator(mode="after")
    def _check_exactly_one_customer_source(self) -> "OrderCreate":
        if (self.customer_id is None) == (self.new_customer is None):
            raise ValueError("Provide exactly one of customer_id or new_customer")
        return self


class OrderItemOut(BaseModel):
    id: int
    product_id: int | None
    description: str | None
    quantity: int
    unit_price: int
    subtotal: int

    model_config = {"from_attributes": True}


class OrderOut(BaseModel):
    id: int
    business_id: int
    customer_id: int | None
    customer_name: str
    customer_phone: str
    delivery_address: str
    delivery_lat: Decimal
    delivery_lng: Decimal
    pickup_address: str | None
    pickup_lat: Decimal | None
    pickup_lng: Decimal | None
    amount: int
    payment_method_id: int
    cash_amount_given: int | None
    notes: str | None
    status: OrderStatus
    driver_id: int | None
    tracking_token: str
    created_at: datetime
    assigned_at: datetime | None
    accepted_at: datetime | None
    picked_up_at: datetime | None
    delivered_at: datetime | None
    items: list[OrderItemOut] = []

    model_config = {"from_attributes": True}


class AssignDriverIn(BaseModel):
    driver_id: int


class OrderStatusTransitionIn(BaseModel):
    status: OrderStatus
    lat: Decimal | None = None
    lng: Decimal | None = None
    note: str | None = None
