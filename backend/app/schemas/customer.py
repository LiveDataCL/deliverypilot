from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# Matches the DB's phone_national generated column, which assumes every phone
# is "+56" + 9 digits (substring(phone from 4)) — an invalid prefix here would
# silently produce a garbage phone_national value instead of erroring.
_PHONE_PATTERN = r"^\+56\d{9}$"


class CustomerCreate(BaseModel):
    phone: str = Field(pattern=_PHONE_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=300)
    address_detail: str | None = Field(default=None, max_length=200)
    lat: Decimal | None = None
    lng: Decimal | None = None
    notes: str | None = None


class CustomerUpdate(BaseModel):
    phone: str | None = Field(default=None, pattern=_PHONE_PATTERN)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = Field(default=None, min_length=1, max_length=300)
    address_detail: str | None = Field(default=None, max_length=200)
    lat: Decimal | None = None
    lng: Decimal | None = None
    notes: str | None = None


class CustomerOut(BaseModel):
    id: int
    business_id: int
    phone: str
    name: str
    address: str
    address_detail: str | None
    lat: Decimal | None
    lng: Decimal | None
    notes: str | None
    order_frequency_days: Decimal | None
    last_order_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomerDefaultIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)


class CustomerDefaultOut(BaseModel):
    product_id: int
    name: str
    quantity: int


class SuggestedItemOut(BaseModel):
    product_id: int
    name: str
    quantity: int
    unit_price: int


class CustomerPrefillOut(BaseModel):
    customer: CustomerOut
    suggested_items: list[SuggestedItemOut]
    # Only two paths are actually implemented (sección 4.2 only describes
    # these two) — "most_frequent" from the spec's example JSON was dropped
    # as redundant with "defaults" per explicit user decision.
    suggestion_source: Literal["last_order", "defaults"]
