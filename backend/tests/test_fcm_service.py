"""Unit tests for app/services/fcm_service.py. No real Firebase project
exists yet (fcm_credentials_json is unset in every test env), so the
unconfigured no-op path is exercised for real; the configured send/failure
paths are exercised via monkeypatching firebase_admin.messaging.send, same
"lightweight fake for an external boundary" approach as
test_geocoding_service.py."""
import pytest
from firebase_admin import messaging

from app.services import fcm_service

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_fcm_service_state(monkeypatch):
    """_app/_warned_unconfigured are module-level state cached across calls
    (deliberately, to avoid re-initializing the Firebase app on every push)
    -- reset them per test so tests don't leak into each other."""
    monkeypatch.setattr(fcm_service, "_app", None)
    monkeypatch.setattr(fcm_service, "_warned_unconfigured", False)


async def test_send_push_is_a_noop_when_unconfigured(monkeypatch):
    """The real state of this project right now: no Firebase project exists,
    fcm_credentials_json is unset. This must degrade to False, never raise."""
    monkeypatch.setattr(fcm_service.settings, "fcm_credentials_json", None)
    result = await fcm_service.send_push("some-token", title="Hola", body="Mensaje")
    assert result is False


async def test_send_push_returns_false_when_token_is_none(monkeypatch):
    """A user with no fcm_token yet (Flutter app doesn't exist, nothing has
    ever written one) -- same degraded, non-raising False, independent of
    whether FCM itself is configured."""
    monkeypatch.setattr(fcm_service, "_get_app", lambda: object())
    result = await fcm_service.send_push(None, title="Hola", body="Mensaje")
    assert result is False


async def test_send_push_returns_true_on_successful_send(monkeypatch):
    monkeypatch.setattr(fcm_service, "_get_app", lambda: object())
    monkeypatch.setattr(messaging, "send", lambda message, app: "projects/x/messages/1")

    result = await fcm_service.send_push("device-token", title="Hola", body="Mensaje")
    assert result is True


async def test_send_push_returns_false_and_does_not_raise_on_send_failure(monkeypatch):
    def _boom(message, app):
        raise RuntimeError("FCM is down")

    monkeypatch.setattr(fcm_service, "_get_app", lambda: object())
    monkeypatch.setattr(messaging, "send", _boom)

    result = await fcm_service.send_push("device-token", title="Hola", body="Mensaje")
    assert result is False
