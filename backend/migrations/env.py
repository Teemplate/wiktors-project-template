"""Alembic environment, async-aware.

Two things here are load-bearing:

1. **The URL comes from the environment, never from alembic.ini.** No credential
   in the repo, and CI/dev/prod each migrate their own database.
2. **`compare_type=True`.** Without it, autogenerate silently misses column type
   changes -- you get an empty revision, commit it, and the type drift only
   surfaces as a runtime error much later.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.db import Base
from app import models  # noqa: F401  -- imported for its side effect: registers tables

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Environment wins; settings supplies the local default.
config.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL", settings.database_url))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a database (`alembic upgrade head --sql`)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
