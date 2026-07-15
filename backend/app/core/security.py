from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]

# bcrypt's hard limit — passlib (unmaintained since 2020) has a known break
# with bcrypt>=4.1 where its own internal truncation-detection logic feeds the
# backend an oversized test string and raises on every single hash/verify call,
# not just for genuinely long passwords. Calling the bcrypt package directly
# sidesteps that broken detection code entirely.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        # Should never happen for /auth/register — RegisterRequest validates
        # this up front — but hash_password has no other caller guarding it.
        raise ValueError(f"Password exceeds bcrypt's {_BCRYPT_MAX_BYTES}-byte limit")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Oversized or malformed input — never let bcrypt's own validation
        # become an unhandled 500 on the login path; just fail the check.
        return False


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
