from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return _pwd_context.verify(plain_password, password_hash)


def _create_token(
    user_id: int, business_id: int, role: str, token_type: TokenType, expires_delta: timedelta
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "business_id": business_id,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, business_id: int, role: str) -> str:
    return _create_token(
        user_id, business_id, role, "access", timedelta(minutes=settings.access_token_expire_minutes)
    )


def create_refresh_token(user_id: int, business_id: int, role: str) -> str:
    return _create_token(
        user_id, business_id, role, "refresh", timedelta(days=settings.refresh_token_expire_days)
    )


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    business_id: int
    role: str
    token_type: TokenType


def decode_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("invalid_token") from exc

    try:
        return TokenPayload(
            user_id=int(payload["sub"]),
            business_id=int(payload["business_id"]),
            role=str(payload["role"]),
            token_type=payload["type"],
        )
    except (KeyError, ValueError) as exc:
        raise ValueError("invalid_token") from exc
