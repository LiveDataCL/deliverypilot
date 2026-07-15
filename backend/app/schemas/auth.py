from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    owner_password: str = Field(min_length=8, max_length=100)
    owner_phone: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    business_id: int
    role: str
    email: str
    phone: str | None
    is_active: bool

    model_config = {"from_attributes": True}
