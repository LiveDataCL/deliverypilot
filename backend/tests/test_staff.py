import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.enums import UserRole
from tests.conftest import create_user_in_business, register_business

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _whoami(client: AsyncClient, access_token: str) -> dict:
    response = await client.get("/api/v1/auth/me", headers=_auth(access_token))
    assert response.status_code == 200
    return response.json()


async def test_create_dispatcher(client: AsyncClient):
    tokens = await register_business(client, business_name="Personal A", email="personalA@example.com")
    headers = _auth(tokens["access_token"])

    response = await client.post(
        "/api/v1/staff",
        json={"email": "dispatcher-a@example.com", "phone": "+56911111111", "role": "dispatcher"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["staff"]["role"] == "dispatcher"
    assert body["staff"]["is_active"] is True
    assert body["staff"]["invite_accepted_at"] is None
    assert body["staff"]["vehicle_type"] is None
    assert body["invite_token"]


async def test_create_driver_requires_vehicle_type(client: AsyncClient):
    tokens = await register_business(client, business_name="Personal B", email="personalB@example.com")
    headers = _auth(tokens["access_token"])

    response = await client.post(
        "/api/v1/staff",
        json={"email": "driver-b@example.com", "role": "driver"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_create_dispatcher_rejects_vehicle_type(client: AsyncClient):
    tokens = await register_business(client, business_name="Personal C", email="personalC@example.com")
    headers = _auth(tokens["access_token"])

    response = await client.post(
        "/api/v1/staff",
        json={"email": "dispatcher-c@example.com", "role": "dispatcher", "vehicle_type": "moto"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_create_driver_with_vehicle_type(client: AsyncClient):
    tokens = await register_business(client, business_name="Personal D", email="personalD@example.com")
    headers = _auth(tokens["access_token"])

    response = await client.post(
        "/api/v1/staff",
        json={"email": "driver-d@example.com", "phone": "+56922222222", "role": "driver", "vehicle_type": "moto"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["staff"]["role"] == "driver"
    assert body["staff"]["vehicle_type"] == "moto"
    assert body["staff"]["driver_status"] == "offline"


async def test_create_staff_rejects_duplicate_email(client: AsyncClient):
    tokens = await register_business(client, business_name="Personal E", email="personalE@example.com")
    headers = _auth(tokens["access_token"])
    await client.post(
        "/api/v1/staff",
        json={"email": "dup-e@example.com", "role": "dispatcher"},
        headers=headers,
    )
    response = await client.post(
        "/api/v1/staff",
        json={"email": "dup-e@example.com", "role": "dispatcher"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "email_taken"


async def test_list_staff_includes_dispatchers_and_drivers(client: AsyncClient):
    tokens = await register_business(client, business_name="Personal F", email="personalF@example.com")
    headers = _auth(tokens["access_token"])
    await client.post(
        "/api/v1/staff", json={"email": "dispatcher-f@example.com", "role": "dispatcher"}, headers=headers
    )
    await client.post(
        "/api/v1/staff",
        json={"email": "driver-f@example.com", "role": "driver", "vehicle_type": "auto"},
        headers=headers,
    )

    response = await client.get("/api/v1/staff", headers=headers)
    assert response.status_code == 200
    roles = {row["role"] for row in response.json()}
    assert roles == {"dispatcher", "driver"}
    # The registering business_owner itself must not show up here.
    emails = {row["email"] for row in response.json()}
    assert "personalF@example.com" not in emails


async def test_staff_are_tenant_isolated(client: AsyncClient):
    tokens_a = await register_business(client, business_name="Personal G", email="personalG@example.com")
    tokens_b = await register_business(client, business_name="Personal H", email="personalH@example.com")
    headers_a = _auth(tokens_a["access_token"])
    headers_b = _auth(tokens_b["access_token"])

    created_b = (
        await client.post(
            "/api/v1/staff", json={"email": "dispatcher-h@example.com", "role": "dispatcher"}, headers=headers_b
        )
    ).json()

    deactivate_response = await client.patch(
        f"/api/v1/staff/{created_b['staff']['id']}/deactivate", headers=headers_a
    )
    assert deactivate_response.status_code == 404


async def test_deactivate_and_activate_staff(client: AsyncClient):
    tokens = await register_business(client, business_name="Personal I", email="personalI@example.com")
    headers = _auth(tokens["access_token"])
    created = (
        await client.post(
            "/api/v1/staff", json={"email": "dispatcher-i@example.com", "role": "dispatcher"}, headers=headers
        )
    ).json()
    staff_id = created["staff"]["id"]

    deactivate_response = await client.patch(f"/api/v1/staff/{staff_id}/deactivate", headers=headers)
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False

    activate_response = await client.patch(f"/api/v1/staff/{staff_id}/activate", headers=headers)
    assert activate_response.status_code == 200
    assert activate_response.json()["is_active"] is True


async def test_driver_role_is_rejected_on_staff_endpoints(client: AsyncClient, db_session):
    tokens = await register_business(
        client, business_name="Personal Driver", email="personaldriver@example.com"
    )
    me = await _whoami(client, tokens["access_token"])
    driver = await create_user_in_business(
        db_session,
        business_id=me["business_id"],
        role=UserRole.driver,
        email="driver-personal@example.com",
    )
    driver_token = create_access_token(driver.id, driver.business_id, UserRole.driver.value)

    response = await client.post(
        "/api/v1/staff",
        json={"email": "no-deberia@example.com", "role": "dispatcher"},
        headers=_auth(driver_token),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden_role"

    list_response = await client.get("/api/v1/staff", headers=_auth(driver_token))
    assert list_response.status_code == 403
    assert list_response.json()["code"] == "forbidden_role"


async def test_deactivated_staff_cannot_login(client: AsyncClient):
    tokens = await register_business(client, business_name="Personal J", email="personalJ@example.com")
    headers = _auth(tokens["access_token"])
    created = (
        await client.post(
            "/api/v1/staff", json={"email": "dispatcher-j@example.com", "role": "dispatcher"}, headers=headers
        )
    ).json()
    accept_response = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": created["invite_token"], "new_password": "ContraseñaSegura123"},
    )
    assert accept_response.status_code == 200, accept_response.text

    await client.patch(f"/api/v1/staff/{created['staff']['id']}/deactivate", headers=headers)

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "dispatcher-j@example.com", "password": "ContraseñaSegura123"},
    )
    assert login_response.status_code == 401
    assert login_response.json()["code"] == "invalid_credentials"
