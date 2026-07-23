import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.tenant import set_tenant_session
from app.models.user import User
from tests.conftest import register_business

pytestmark = pytest.mark.asyncio


async def test_update_fcm_token_requires_a_valid_access_token(client: AsyncClient):
    response = await client.patch("/api/v1/auth/me/fcm-token", json={"fcm_token": "some-device-token"})
    assert response.status_code == 401


async def test_update_fcm_token_persists_it_on_the_authenticated_users_own_account(
    client: AsyncClient, db_session
):
    tokens = await register_business(client, business_name="Negocio FCM", email="fcm1@example.com")
    response = await client.patch(
        "/api/v1/auth/me/fcm-token",
        json={"fcm_token": "device-token-abc123"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "fcm1@example.com"

    user = await db_session.scalar(select(User).where(User.email == "fcm1@example.com"))
    assert user.fcm_token == "device-token-abc123"


async def test_update_fcm_token_rejects_an_empty_token(client: AsyncClient):
    tokens = await register_business(client, business_name="Negocio FCM2", email="fcm2@example.com")
    response = await client.patch(
        "/api/v1/auth/me/fcm-token",
        json={"fcm_token": ""},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 422


async def test_register_creates_business_and_owner_and_returns_tokens(client: AsyncClient):
    tokens = await register_business(
        client, business_name="Aguas Test SpA", email="owner1@example.com"
    )
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"


async def test_register_rejects_duplicate_email(client: AsyncClient):
    await register_business(client, business_name="Negocio A", email="dup@example.com")
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "business_name": "Negocio B",
            "owner_email": "dup@example.com",
            "owner_password": "OtraClave123",
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "email_taken"


async def test_login_with_correct_credentials_succeeds(client: AsyncClient):
    await register_business(
        client, business_name="Negocio Login", email="login1@example.com", password="ClaveCorrecta123"
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": "login1@example.com", "password": "ClaveCorrecta123"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


async def test_login_with_wrong_password_returns_401_with_consistent_error_shape(client: AsyncClient):
    await register_business(
        client, business_name="Negocio Login2", email="login2@example.com", password="ClaveCorrecta123"
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": "login2@example.com", "password": "ClaveIncorrecta"}
    )
    assert response.status_code == 401
    body = response.json()
    assert set(body.keys()) == {"detail", "code"}
    assert body["code"] == "invalid_credentials"


async def test_me_requires_a_valid_access_token(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401

    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


async def test_me_returns_the_authenticated_users_own_profile(client: AsyncClient):
    tokens = await register_business(client, business_name="Negocio Me", email="me1@example.com")
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "me1@example.com"
    assert body["role"] == "business_owner"


async def test_refresh_issues_a_new_token_pair(client: AsyncClient):
    tokens = await register_business(client, business_name="Negocio Refresh", email="refresh1@example.com")
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"] != tokens["access_token"]


async def test_refresh_rejects_an_access_token_used_as_a_refresh_token(client: AsyncClient):
    tokens = await register_business(client, business_name="Negocio Refresh2", email="refresh2@example.com")
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert response.status_code == 401
    assert response.json()["code"] == "wrong_token_type"


async def test_deactivated_user_is_locked_out_immediately_not_only_on_refresh(
    client: AsyncClient, db_session
):
    """CLAUDE.md's requirement: is_active is re-checked on every request via the
    tenant dependency, not only when refreshing — so a still-valid access token
    stops working the moment the user is deactivated, without waiting for it to
    expire or for the client to hit /refresh."""
    tokens = await register_business(client, business_name="Negocio Deact", email="deact1@example.com")

    ok_response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert ok_response.status_code == 200

    user = await db_session.scalar(select(User).where(User.email == "deact1@example.com"))
    # users' UPDATE policy is tenant-scoped (migration 0002) — only its SELECT
    # is deliberately unrestricted, for the login-by-email lookup. A raw test
    # write has to set the tenant context first, same as any real write path.
    await set_tenant_session(db_session, user.business_id)
    user.is_active = False
    await db_session.commit()

    blocked_response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert blocked_response.status_code == 401
    assert blocked_response.json()["code"] == "inactive_user"
