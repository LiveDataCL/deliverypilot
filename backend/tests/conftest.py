"""Global pytest fixtures.

IMPORTANT ordering: DATABASE_URL and MIGRATIONS_DATABASE_URL are overridden to
their TEST_* equivalents here, before any `app.*` module is imported, because
app.db.base creates the async engine at import time from
app.core.config.settings. Every fixture/test in this suite runs against the
*_test database as a result — never against the dev database.

Two roles, two URLs (see db/init/01-create-app-role.sql for the full reasoning):
DATABASE_URL/TEST_DATABASE_URL is the ordinary, non-superuser role the app and
this test suite query as (RLS applies to it normally). MIGRATIONS_DATABASE_URL/
TEST_MIGRATIONS_DATABASE_URL is the bootstrap superuser, used only to run
Alembic — it owns the tables and needs privileges the runtime role doesn't have.

Schema reset (Alembic downgrade + upgrade) happens ONCE per test session, not
per test — committed rows from one test persist for the rest of the run. Tests
rely on globally-unique emails/business names rather than per-test transaction
rollback, which keeps the RLS tests (test_rls.py) able to use real commits
across multiple sessions/connections instead of being nested inside a rolled-
back outer transaction. Don't write a test that asserts a total row count.

Event loop note: pytest-asyncio's default (and least version-fragile) behavior
gives each test function its own event loop. app.db.base.engine is a
module-level singleton (correct for the real app — one process, one loop, for
the app's whole lifetime), so its connection pool must not carry a connection
from one test's loop into another test's loop. Rather than fight pytest-asyncio's
loop-scope configuration, `_dispose_shared_engine_after_test` below just closes
the pool after every test, so the next test's first query always opens a fresh
connection bound to its own loop.
"""
import asyncio
import os
from pathlib import Path

from dotenv import dotenv_values

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_env = dotenv_values(_BACKEND_DIR / ".env")
if _env.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _env["TEST_DATABASE_URL"]
if _env.get("TEST_MIGRATIONS_DATABASE_URL"):
    os.environ["MIGRATIONS_DATABASE_URL"] = _env["TEST_MIGRATIONS_DATABASE_URL"]

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.base import async_session_factory, engine  # noqa: E402
from app.main import app  # noqa: E402


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    # The bootstrap-superuser role, not the app's runtime role — same as
    # alembic/env.py; migrations need privileges the runtime role lacks.
    cfg.set_main_option("sqlalchemy.url", get_settings().migrations_database_url)
    return cfg


def _assert_db_role_is_not_superuser() -> None:
    """Regression guard for the exact failure mode RLS depends on not having:
    the official postgres Docker image makes POSTGRES_USER (the bootstrap
    role) a superuser via initdb, and superusers bypass Row-Level Security
    unconditionally — FORCE ROW LEVEL SECURITY does not override that. This
    checks the RUNTIME role (DATABASE_URL / TEST_DATABASE_URL, e.g.
    deliverypilot_app) — not the migrations role, which is expected to be the
    superuser. If the runtime role is ever superuser (DATABASE_URL
    misconfigured to point at the bootstrap role again), every RLS test would
    pass for the wrong reason — appearing to prove isolation while the
    policies are silently inert. Fail loudly here instead, before any test
    gets a chance to give a false pass.
    """

    async def _check() -> tuple[bool, bool]:
        check_engine = create_async_engine(get_settings().database_url)
        try:
            async with check_engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
                )
                return result.one()
        finally:
            await check_engine.dispose()

    rolsuper, rolbypassrls = asyncio.run(_check())
    assert not rolsuper and not rolbypassrls, (
        "The role DATABASE_URL connects as is superuser or has BYPASSRLS — Postgres "
        "lets such roles bypass Row-Level Security unconditionally, even with FORCE "
        "ROW LEVEL SECURITY. Every RLS test would pass for the wrong reason. DATABASE_URL "
        "must be the ordinary deliverypilot_app role, not the deliverypilot bootstrap "
        "role — see db/init/01-create-app-role.sql."
    )


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations():
    """Runs the real Alembic migrations (schema + RLS) once per test session.

    This must be actual migrations, not Base.metadata.create_all(): RLS policies
    are raw SQL inside migration 0002, which create_all() knows nothing about —
    using it here would let every RLS test pass for the wrong reason (no policies
    at all rather than working policies).
    """
    settings = get_settings()
    assert "test" in settings.database_url and "test" in settings.migrations_database_url, (
        "Refusing to run migrations: DATABASE_URL or MIGRATIONS_DATABASE_URL does not "
        f"look like a test database ({settings.database_url!r}, "
        f"{settings.migrations_database_url!r}). Set TEST_DATABASE_URL and "
        "TEST_MIGRATIONS_DATABASE_URL in backend/.env and make sure both point at a "
        "*_test database, never at dev/prod."
    )
    cfg = _alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    _assert_db_role_is_not_superuser()
    yield


@pytest_asyncio.fixture(autouse=True)
async def _dispose_shared_engine_after_test():
    """See the event-loop note in this file's module docstring."""
    yield
    await engine.dispose()


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
