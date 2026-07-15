"""The mandatory tenant-isolation test (CLAUDE.md §5): a user from business A
must never be able to read a resource belonging to business B. This test is
never deleted, even once Fase 1 adds real CRUD endpoints — extend it, don't
replace it.
"""
import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from tests.conftest import register_business

pytestmark = pytest.mark.asyncio


async def _whoami(client: AsyncClient, access_token: str) -> dict:
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200
    return response.json()


async def test_business_a_cannot_read_business_bs_user_by_id(client: AsyncClient):
    tokens_a = await register_business(client, business_name="Negocio A", email="ownerA@example.com")
    tokens_b = await register_business(client, business_name="Negocio B", email="ownerB@example.com")

    me_b = await _whoami(client, tokens_b["access_token"])
    b_user_id = me_b["id"]

    # Sanity check: B can read its own user by id.
    own_response = await client.get(
        f"/api/v1/users/{b_user_id}", headers={"Authorization": f"Bearer {tokens_b['access_token']}"}
    )
    assert own_response.status_code == 200

    # The actual isolation assertion: A asking for B's resource gets 404, never
    # B's data, regardless of A knowing B's user_id.
    cross_tenant_response = await client.get(
        f"/api/v1/users/{b_user_id}", headers={"Authorization": f"Bearer {tokens_a['access_token']}"}
    )
    assert cross_tenant_response.status_code in (403, 404)
    assert "email" not in cross_tenant_response.text


async def test_business_a_cannot_read_its_own_id_under_a_forged_business_id_claim(client: AsyncClient):
    """Even if a JWT's business_id claim is tampered with (impossible without the
    signing secret, but this is what would happen if it somehow occurred), the
    app must not let a user assume a different tenant's identity: the
    (user_id, business_id) pair simply won't exist, so the request is rejected
    outright rather than silently resolving against the "wrong" business_id."""
    tokens_a = await register_business(client, business_name="Negocio C", email="ownerC@example.com")
    tokens_b = await register_business(client, business_name="Negocio D", email="ownerD@example.com")

    me_a = await _whoami(client, tokens_a["access_token"])
    me_b = await _whoami(client, tokens_b["access_token"])

    forged_token = create_access_token(
        user_id=me_a["id"], business_id=me_b["business_id"], role="business_owner"
    )
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged_token}"})
    assert response.status_code == 401
    assert response.json()["code"] == "inactive_user"
