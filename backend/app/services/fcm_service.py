"""FCM push notifications via firebase-admin. Degrades gracefully: if
fcm_credentials_json isn't set (no Firebase project exists yet -- see the
FCM/WebSocket/map scoping notes), every send_push call is a no-op that logs
a warning once, the same tolerance CLAUDE.md §2 already requires for
Nominatim/OSRM/R2. Never raises -- a push failure or missing config must
never break the order-assignment flow that triggered it.
"""
import asyncio
import json
import logging

import firebase_admin
from firebase_admin import credentials, messaging

from app.core.config import settings

logger = logging.getLogger(__name__)

_app: firebase_admin.App | None = None
_warned_unconfigured = False


def _get_app() -> firebase_admin.App | None:
    global _app, _warned_unconfigured
    if _app is not None:
        return _app
    if not settings.fcm_credentials_json:
        if not _warned_unconfigured:
            logger.warning(
                "fcm_credentials_json is not set -- push notifications are disabled (no-op) "
                "until a real Firebase service-account JSON is provided"
            )
            _warned_unconfigured = True
        return None
    cred = credentials.Certificate(json.loads(settings.fcm_credentials_json))
    _app = firebase_admin.initialize_app(cred)
    return _app


async def send_push(
    fcm_token: str | None, *, title: str, body: str, data: dict[str, str] | None = None
) -> bool:
    """Returns True only if the push was actually handed to FCM. False for
    every degraded case (unconfigured, no token on the target user, send
    failure) -- callers must treat False as "did not send", never as an
    error to propagate."""
    app = _get_app()
    if app is None or not fcm_token:
        return False

    message = messaging.Message(
        # token= (deprecated in favor of fid= as of firebase-admin 7.5.0) is
        # deliberate, not an oversight: fid is a Firebase Installation ID, a
        # different targeting mechanism (Firebase Installations, not FCM).
        # fcm_token on the User model is a plain FCM device registration
        # token -- token= is the correct parameter for that, regardless of
        # the deprecation warning.
        token=fcm_token,
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        # SPEC.md's "push FCM al repartidor con sonido/prioridad alta".
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(sound="default", priority="high"),
        ),
    )
    try:
        # messaging.send is synchronous (blocking network I/O) -- run it off
        # the event loop rather than stalling every other request on it.
        await asyncio.to_thread(messaging.send, message, app=app)
        return True
    except Exception:
        logger.exception("FCM push failed")
        return False
