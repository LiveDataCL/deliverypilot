import asyncio
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Windows' default event loop policy (ProactorEventLoop) is unreliable with
# asyncpg's overlapped I/O socket handling — this affects any asyncpg
# connection opened under it, independent of how many event loops get
# created. Only matters for standalone CLI usage here (`alembic upgrade head`
# run directly) — when run through the test suite, tests/conftest.py sets
# this same policy before this module ever runs, and that module-level
# connection-reuse path below doesn't call asyncio.run() at all.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Import the app's Base and every model module so Base.metadata is fully
# populated before autogenerate (or downgrade table-drop ordering) runs.
import app.models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base

config = context.config
# Migrations run as the bootstrap superuser, not the app's runtime role — it
# owns every table and needs privileges (CREATE TABLE/TYPE, FORCE ROW LEVEL
# SECURITY, CREATE POLICY) the restricted app role deliberately doesn't have.
config.set_main_option("sqlalchemy.url", get_settings().migrations_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
elif config.attributes.get("connection") is not None:
    # Programmatic/test usage: the caller already has an async connection open
    # within its own event loop (see tests/conftest.py) and hands it in here
    # directly instead of us creating a new engine and calling asyncio.run()
    # ourselves. Originally added to cut down on repeated asyncio.run() calls
    # per test session; that turned out not to be the cause of the Windows
    # ConnectionDoesNotExistError failures (see the WindowsSelectorEventLoopPolicy
    # note at the top of this file for the actual cause) but the pattern is
    # still correct practice — one shared connection/transaction for the
    # whole downgrade+upgrade sequence, not a fresh engine per command.
    do_run_migrations(config.attributes["connection"])
else:
    asyncio.run(run_migrations_online())
