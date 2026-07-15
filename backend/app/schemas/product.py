from pydantic import BaseModel, Field


class ComboItemIn(BaseModel):
    component_product_id: int
    quantity: int = Field(gt=0)


class ComboItemOut(BaseModel):
    id: int
    component_product_id: int
    quantity: int

    model_config = {"from_attributes": True}


class PriceTierIn(BaseModel):
    min_quantity: int = Field(gt=0)
    unit_price: int = Field(ge=0)


class PriceTierOut(BaseModel):
    id: int
    min_quantity: int
    unit_price: int

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    price: int = Field(ge=0)
    unit: str = Field(min_length=1, max_length=30)
    is_combo: bool = False
    # Plain URL text for now — actual image hosting (Cloudflare R2) is Fase 3.
    image_url: str | None = Field(default=None, max_length=500)
    active: bool = True
    sort_order: int = 0


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    price: int | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    is_combo: bool | None = None
    image_url: str | None = Field(default=None, max_length=500)
    active: bool | None = None
    sort_order: int | None = None


class ProductOut(BaseModel):
    id: int
    business_id: int
    name: str
    description: str | None
    price: int
    unit: str
    active: bool
    is_combo: bool
    image_url: str | None
    sort_order: int
    combo_items: list[ComboItemOut] = []
    price_tiers: list[PriceTierOut] = []

    model_config = {"from_attributes": True}
