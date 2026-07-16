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

`_apply_migrations` note: downgrade, upgrade, and the role safety-check all run
inside exactly one asyncio.run() call (`_setup_test_database`), instead of one
asyncio.run() per Alembic command (Alembic's `command.downgrade`/`command.upgrade`
each independently re-execute alembic/env.py, including its own
`asyncio.run(run_migrations_online())`, unless handed an existing connection —
see env.py's `config.attributes.get("connection")` branch). Repeated
asyncio.run() calls in one process — three of them here, back to back, each
tearing down a real asyncpg connection/event loop — is the suspected cause of
Windows-only `ConnectionDoesNotExistError` failures that don't reproduce on
Linux CI.

UPDATE: consolidating to one asyncio.run() call (above) did NOT fix the
Windows failure — same ConnectionDoesNotExistError, same 34 tests, confirmed
by re-running on Windows. That rules out "repeated event loops" as the cause.
The real issue: Windows' default event loop policy is ProactorEventLoop, and
asyncpg's overlapped I/O socket handling is unreliable under it independent of
how many loops get created — this affects every asyncpg connection opened
under a Proactor loop, not just the migration fixture's. pytest-asyncio
creates its own event loop per test function (not via asyncio.run(), but via
its own internal loop creation, under whatever policy is globally active at
that time) — so every test using `client`/`db_session` was equally exposed,
which is why fixing only the migration fixture's own asyncio.run() call moved
nothing. Setting the event loop policy to WindowsSelectorEventLoopPolicy here,
before pytest_asyncio is even imported, is process-global and applies to
every loop created for the rest of the test run — both this file's own
asyncio.run() call and every one pytest-asyncio creates per test.
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import async_session_factory, engine  # noqa: E402
from app.db.tenant import set_tenant_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.user import User  # noqa: E402


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    # The bootstrap-superuser role, not the app's runtime role — same as
    # alembic/env.py; migrations need privileges the runtime role lacks.
    cfg.set_main_option("sqlalchemy.url", get_settings().migrations_database_url)
    return cfg


def _run_downgrade(connection) -> None:
    cfg = _alembic_config()
    cfg.attributes["connection"] = connection
    command.downgrade(cfg, "base")


def _run_upgrade(connection) -> None:
    cfg = _alembic_config()
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


async def _setup_test_database() -> tuple[bool, bool]:
    """Downgrade, upgrade, and the role safety-check, all inside this one
    coroutine — see the event-loop / _apply_migrations note in this file's
    module docstring for why that matters.

    This must be actual migrations, not Base.metadata.create_all(): RLS
    policies are raw SQL inside migration 0002, which create_all() knows
    nothing about — using it here would let every RLS test pass for the wrong
    reason (no policies at all rather than working policies).
    """
    migrations_engine = create_async_engine(
        get_settings().migrations_database_url, poolclass=NullPool
    )
    try:
        async with migrations_engine.connect() as connection:
            await connection.run_sync(_run_downgrade)
            await connection.run_sync(_run_upgrade)
    finally:
        await migrations_engine.dispose()

    # Regression guard for the exact failure mode RLS depends on not having:
    # the official postgres Docker image makes POSTGRES_USER (the bootstrap
    # role) a superuser via initdb, and superusers bypass Row-Level Security
    # unconditionally — FORCE ROW LEVEL SECURITY does not override that. This
    # checks the RUNTIME role (DATABASE_URL / TEST_DATABASE_URL, e.g.
    # deliverypilot_app) — not the migrations role, which is expected to be
    # the superuser. If the runtime role is ever superuser (DATABASE_URL
    # misconfigured to point at the bootstrap role again), every RLS test
    # would pass for the wrong reason — appearing to prove isolation while
    # the policies are silently inert.
    check_engine = create_async_engine(get_settings().database_url)
    try:
        async with check_engine.connect() as connection:
            result = await connection.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
            return result.one()
    finally:
        await check_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations():
    settings = get_settings()
    assert "test" in settings.database_url and "test" in settings.migrations_database_url, (
        "Refusing to run migrations: DATABASE_URL or MIGRATIONS_DATABASE_URL does not "
        f"look like a test database ({settings.database_url!r}, "
        f"{settings.migrations_database_url!r}). Set TEST_DATABASE_URL and "
        "TEST_MIGRATIONS_DATABASE_URL in backend/.env and make sure both point at a "
        "*_test database, never at dev/prod."
    )
    rolsuper, rolbypassrls = asyncio.run(_setup_test_database())
    assert not rolsuper and not rolbypassrls, (
        "The role DATABASE_URL connects as is superuser or has BYPASSRLS — Postgres "
        "lets such roles bypass Row-Level Security unconditionally, even with FORCE "
        "ROW LEVEL SECURITY. Every RLS test would pass for the wrong reason. DATABASE_URL "
        "must be the ordinary deliverypilot_app role, not the deliverypilot bootstrap "
        "role — see db/init/01-create-app-role.sql."
    )
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


async def create_user_in_business(
    db_session: AsyncSession,
    *,
    business_id: int,
    role: UserRole,
    email: str,
    password: str = "ContraseñaSegura123",
) -> User:
    """Creates a user with an arbitrary role directly, for tests that need a
    role Personal management doesn't have an endpoint for yet (e.g. a driver
    account, to test that catalog writes reject that role) — bypasses the
    HTTP layer since there's no "create teammate" endpoint to go through
    until the Personal sub-module is built."""
    await set_tenant_session(db_session, business_id)
    user = User(
        business_id=business_id, role=role, email=email, password_hash=hash_password(password)
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user
