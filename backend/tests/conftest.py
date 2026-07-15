"""Global pytest fixtures.

IMPORTANT ordering: DATABASE_URL is overridden to TEST_DATABASE_URL here, before
any `app.*` module is imported, because app.db.base creates the async engine at
import time from app.core.config.settings. Every fixture/test in this suite runs
against TEST_DATABASE_URL as a result — never against the dev database.

Schema reset (Alembic downgrade + upgrade) happens ONCE per test session, not
per test — committed rows from one test persist for the rest of the run. Tests
rely on globally-unique emails/business names rather than per-test transaction
rollback, which keeps the RLS tests (test_rls.py) able to use real commits
across multiple sessions/connections instead of being nested inside a rolled-
back outer transaction. Don't write a test that asserts a total row count.
"""
import os
from pathlib import Path

from dotenv import dotenv_values

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_env = dotenv_values(_BACKEND_DIR / ".env")
if _env.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _env["TEST_DATABASE_URL"]

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.base import async_session_factory  # noqa: E402
from app.main import app  # noqa: E402


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations():
    """Runs the real Alembic migrations (schema + RLS) once per test session.

    This must be actual migrations, not Base.metadata.create_all(): RLS policies
    are raw SQL inside migration 0002, which create_all() knows nothing about —
    using it here would let every RLS test pass for the wrong reason (no policies
    at all rather than working policies).
    """
    settings = get_settings()
    assert "test" in settings.database_url, (
        "Refusing to run migrations: DATABASE_URL does not look like a test "
        f"database ({settings.database_url!r}). Set TEST_DATABASE_URL in backend/.env "
        "and make sure it points at a *_test database, never at dev/prod."
    )
    cfg = _alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    # Relies on AsyncSession's autobegin (a transaction starts lazily on first
    # statement) rather than wrapping in `session.begin()`, so tests are free to
    # call session.commit()/rollback() explicitly mid-test without fighting an
    # outer transaction context.
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def register_business(client: AsyncClient, *, business_name: str, email: str, password: str = "ContraseñaSegura123"):
    """Shared by every test that needs a fresh, real tenant — goes through the
    actual /auth/register endpoint rather than inserting rows directly, so tests
    exercise the same code path production traffic does."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "business_name": business_name,
            "owner_email": email,
            "owner_password": password,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
