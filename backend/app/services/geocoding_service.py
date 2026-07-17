import logging
from decimal import Decimal

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def geocode_address(address: str) -> tuple[Decimal, Decimal] | None:
    """Resolves a street address to (lat, lng) via Nominatim. Returns None on
    any failure (timeout, non-200, no results, unexpected shape) rather than
    raising — CLAUDE.md §2 requires external calls to degrade with a clear
    fallback, not crash the request; callers decide what that fallback is.
    No retry loop here: order creation has a <10s acceptance target
    (SPEC.md §1 E2E criteria), so this fails fast rather than retrying."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.nominatim_url}/search",
                params={"q": address, "format": "json", "limit": 1},
                # Nominatim's usage policy requires an identifying User-Agent.
                headers={"User-Agent": "DeliveryPilot/1.0"},
            )
            response.raise_for_status()
            results = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Nominatim geocoding failed for address=%r: %s", address, exc)
        return None

    if not results:
        return None

    try:
        return Decimal(str(results[0]["lat"])), Decimal(str(results[0]["lon"]))
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning("Nominatim returned an unexpected shape for address=%r: %s", address, exc)
        return None
