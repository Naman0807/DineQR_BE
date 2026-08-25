import asyncio
import os
import sys
from logging.config import fileConfig
from dotenv import load_dotenv

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine  # Added for async support

# Ensure .env variables are loaded into the process environment first.
# DATABASE_URL from the OS/env file should be used if present, otherwise fall back to alembic.ini.
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(base_dir, ".env"))

config = context.config
sqlalchemy_url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))

sys.path.append(base_dir)

from app.database import Base
from app.models.models import * # noqa: F401, F403

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = sqlalchemy_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Synchronous context executor required by Alembic."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Asynchronous wrapper around the online migration runner."""
    # Create an async-compatible engine directly from the environment URL
    connectable = create_async_engine(
        sqlalchemy_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # Pass the sync migration steps into the async runner
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # Handle the event loop to drive the async migration execution
    asyncio.run(run_migrations_online())