from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.business_id, user.role.value),
        refresh_token=create_refresh_token(user.id, user.business_id, user.role.value),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    if await auth_service.find_by_email(db, payload.owner_email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Ya existe una cuenta con ese email", "code": "email_taken"},
        )

    try:
        user = await auth_service.register_business_owner(
            db,
            business_name=payload.business_name,
            email=payload.owner_email,
            password=payload.owner_password,
            phone=payload.owner_phone,
        )
    except IntegrityError as exc:
        # Two concurrent /register calls for the same email can both pass the
        # find_by_email check above before either commits — the DB's unique
        # constraint on users.email is the real guard; this just turns that
        # race into the same clean 409 instead of a raw 500.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Ya existe una cuenta con ese email", "code": "email_taken"},
        ) from exc

    return _issue_tokens(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await auth_service.authenticate(db, email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Email o contrasena incorrectos", "code": "invalid_credentials"},
        )
    return _issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        token_payload = decode_token(payload.refresh_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Refresh token invalido o expirado", "code": "invalid_token"},
        ) from exc

    if token_payload.token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Se requiere un refresh token", "code": "wrong_token_type"},
        )

    user = await auth_service.get_active_user(
        db, user_id=token_payload.user_id, business_id=token_payload.business_id
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Usuario inactivo o inexistente", "code": "inactive_user"},
        )

    return _issue_tokens(user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
