from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    # max_length is a char count; bcrypt's real limit is 72 BYTES, so a
    # UTF-8 password with multi-byte characters could pass this and still
    # overflow bcrypt — the validator below checks the actual encoded length.
    owner_password: str = Field(min_length=8, max_length=100)
    owner_phone: str | None = None

    @field_validator("owner_password")
    @classmethod
    def _password_must_fit_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contrasena no puede superar los 72 bytes")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class FcmTokenUpdateRequest(BaseModel):
    fcm_token: str = Field(min_length=1, max_length=255)


class UserOut(BaseModel):
    id: int
    business_id: int
    role: str
    email: str
    phone: str | None
    is_active: bool

    model_config = {"from_attributes": True}
