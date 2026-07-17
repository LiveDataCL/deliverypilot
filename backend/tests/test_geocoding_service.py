from decimal import Decimal

import httpx
import pytest

from app.services.geocoding_service import geocode_address

pytestmark = pytest.mark.asyncio


def _patch_client(monkeypatch, handler) -> None:
    # app.services.geocoding_service.httpx IS the same module object as this
    # file's own `httpx` import (modules are singletons) -- patching
    # AsyncClient on it patches the real thing globally. factory must call
    # the ORIGINAL AsyncClient, captured before patching, or it recurses
    # into itself infinitely.
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr("app.services.geocoding_service.httpx.AsyncClient", factory)


async def test_geocode_address_returns_lat_lng_on_success(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "Calle Falsa 123"
        return httpx.Response(200, json=[{"lat": "-33.456", "lon": "-70.648"}])

    _patch_client(monkeypatch, handler)

    result = await geocode_address("Calle Falsa 123")
    assert result == (Decimal("-33.456"), Decimal("-70.648"))


async def test_geocode_address_returns_none_on_empty_results(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    _patch_client(monkeypatch, handler)

    result = await geocode_address("Direccion inexistente")
    assert result is None


async def test_geocode_address_returns_none_on_http_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    _patch_client(monkeypatch, handler)

    result = await geocode_address("Cualquier direccion")
    assert result is None


async def test_geocode_address_returns_none_on_timeout(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _patch_client(monkeypatch, handler)

    result = await geocode_address("Cualquier direccion")
    assert result is None


async def test_geocode_address_returns_none_on_malformed_shape(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"unexpected": "shape"}])

    _patch_client(monkeypatch, handler)

    result = await geocode_address("Cualquier direccion")
    assert result is None
