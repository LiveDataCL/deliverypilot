import pytest
from httpx import AsyncClient

from app.core import security
from tests.conftest import register_business

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_dispatcher(client: AsyncClient, headers: dict, email: str) -> dict:
    response = await client.post(
        "/api/v1/staff", json={"email": email, "role": "dispatcher"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_accept_invite_sets_password_and_logs_in(client: AsyncClient):
    tokens = await register_business(client, business_name="Invite A", email="inviteA@example.com")
    headers = _auth(tokens["access_token"])
    created = await _create_dispatcher(client, headers, "invitee-a@example.com")

    accept_response = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": created["invite_token"], "new_password": "NuevaContraseña123"},
    )
    assert accept_response.status_code == 200, accept_response.text
    body = accept_response.json()
    assert body["access_token"]
    assert body["refresh_token"]

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "invitee-a@example.com", "password": "NuevaContraseña123"},
    )
    assert login_response.status_code == 200


async def test_accept_invite_sets_invite_accepted_at_and_activates(client: AsyncClient):
    tokens = await register_business(client, business_name="Invite B", email="inviteB@example.com")
    headers = _auth(tokens["access_token"])
    created = await _create_dispatcher(client, headers, "invitee-b@example.com")
    assert created["staff"]["invite_accepted_at"] is None

    await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": created["invite_token"], "new_password": "NuevaContraseña123"},
    )

    staff_list = (await client.get("/api/v1/staff", headers=headers)).json()
    updated = next(s for s in staff_list if s["id"] == created["staff"]["id"])
    assert updated["invite_accepted_at"] is not None
    assert updated["is_active"] is True


async def test_accept_invite_rejects_an_access_token(client: AsyncClient):
    tokens = await register_business(client, business_name="Invite C", email="inviteC@example.com")

    response = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": tokens["access_token"], "new_password": "NuevaContraseña123"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "wrong_token_type"


async def test_accept_invite_rejects_an_expired_token(client: AsyncClient, monkeypatch):
    tokens = await register_business(client, business_name="Invite D", email="inviteD@example.com")
    headers = _auth(tokens["access_token"])

    monkeypatch.setattr(security.settings, "invite_token_expire_days", -1)
    created = await _create_dispatcher(client, headers, "invitee-d@example.com")

    response = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": created["invite_token"], "new_password": "NuevaContraseña123"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_token"


async def test_accept_invite_rejects_a_replayed_already_used_token(client: AsyncClient):
    """The core single-use guarantee: the SAME token, presented a second
    time after it already succeeded once, must be rejected — not silently
    allow overwriting the password again."""
    tokens = await register_business(client, business_name="Invite E", email="inviteE@example.com")
    headers = _auth(tokens["access_token"])
    created = await _create_dispatcher(client, headers, "invitee-e@example.com")

    first_attempt = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": created["invite_token"], "new_password": "PrimeraContraseña123"},
    )
    assert first_attempt.status_code == 200, first_attempt.text

    replay_attempt = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": created["invite_token"], "new_password": "SegundaContraseña456"},
    )
    assert replay_attempt.status_code == 400
    assert replay_attempt.json()["code"] == "token_superseded"

    # The password from the first (legitimate) accept must still be the one
    # that works -- the replay must not have changed anything.
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "invitee-e@example.com", "password": "PrimeraContraseña123"},
    )
    assert login_response.status_code == 200


async def test_reset_password_invalidates_the_previous_invite_link(client: AsyncClient):
    """The other half of the single-use guarantee: issuing a NEW link (an
    admin-triggered reset) must invalidate an older, still-unused one --
    not just tokens that were already consumed."""
    tokens = await register_business(client, business_name="Invite F", email="inviteF@example.com")
    headers = _auth(tokens["access_token"])
    created = await _create_dispatcher(client, headers, "invitee-f@example.com")
    old_token = created["invite_token"]

    reset_response = await client.post(
        f"/api/v1/staff/{created['staff']['id']}/reset-password", headers=headers
    )
    assert reset_response.status_code == 200, reset_response.text
    new_token = reset_response.json()["invite_token"]
    assert new_token != old_token

    old_token_attempt = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": old_token, "new_password": "IntentoConLinkViejo123"},
    )
    assert old_token_attempt.status_code == 400
    assert old_token_attempt.json()["code"] == "token_superseded"

    new_token_attempt = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": new_token, "new_password": "ContraseñaConLinkNuevo123"},
    )
    assert new_token_attempt.status_code == 200, new_token_attempt.text


async def test_reset_password_does_not_reset_invite_accepted_at(client: AsyncClient):
    """A reset on an already-accepted staff member must not make the panel
    show them as "Invitado" again -- invite_accepted_at is set once, at
    first acceptance, and a later reset doesn't touch it."""
    tokens = await register_business(client, business_name="Invite G", email="inviteG@example.com")
    headers = _auth(tokens["access_token"])
    created = await _create_dispatcher(client, headers, "invitee-g@example.com")

    await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": created["invite_token"], "new_password": "PrimeraContraseña123"},
    )
    first_accept_time = next(
        s for s in (await client.get("/api/v1/staff", headers=headers)).json()
        if s["id"] == created["staff"]["id"]
    )["invite_accepted_at"]
    assert first_accept_time is not None

    reset_response = await client.post(
        f"/api/v1/staff/{created['staff']['id']}/reset-password", headers=headers
    )
    await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": reset_response.json()["invite_token"], "new_password": "SegundaContraseña456"},
    )

    staff_list = (await client.get("/api/v1/staff", headers=headers)).json()
    updated = next(s for s in staff_list if s["id"] == created["staff"]["id"])
    assert updated["invite_accepted_at"] == first_accept_time
