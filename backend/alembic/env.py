import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

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
    # ourselves. This is what lets the test suite run downgrade + upgrade (and
    # anything else) inside exactly one asyncio.run() for the whole session,
    # instead of once per command.*() call — repeated asyncio.run() calls in
    # one process is the suspected cause of Windows-only
    # ConnectionDoesNotExistError failures with asyncpg (each call tears down
    # a real connection/event loop in quick succession; normal `alembic`
    # CLI/production usage below is a single call and is unaffected).
    do_run_migrations(config.attributes["connection"])
else:
    asyncio.run(run_migrations_online())
