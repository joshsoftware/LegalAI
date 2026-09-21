import asyncio
from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from db.config import settings
from db.database import Base
import db.models  # noqa: F401  (registers models on Base.metadata for autogenerate)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Alembic builds alembic_version.version_num as VARCHAR(32), but this project
# uses descriptive revision ids and two already exceed that:
#   "0006_create_intermediate_field_mapping_table" (44 chars)
#   "0009_add_salary_continuity_check_type"        (37 chars)
# On a genuinely fresh database the chain died at 0007 with
# StringDataRightTruncationError. Existing databases only survived because
# their column had been widened to VARCHAR(255) at some point by hand, which
# is why this went unnoticed.
#
# Widening is the non-breaking fix: shortening the revision ids instead would
# orphan any database currently sitting on one of them ("Can't locate revision
# identified by ..."), requiring manual UPDATEs everywhere it is deployed.
#
# This is done as plain DDL rather than through Alembic's own configuration
# because that configuration keeps moving: the old `version_table_column_type`
# option to context.configure() was removed (alembic 1.19 hardcodes String(32)
# in DefaultImpl.version_table_impl), and because configure() accepts **kw, a
# stale option is silently ignored rather than raising. Explicit SQL does not
# depend on which alembic version is installed.
_ENSURE_VERSION_TABLE_WIDTH = (
    # Created up front so Alembic finds an existing (correctly sized) table
    # instead of creating a VARCHAR(32) one itself.
    """
    CREATE TABLE IF NOT EXISTS alembic_version (
        version_num VARCHAR(255) NOT NULL,
        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
    )
    """,
    # No-op when already 255; widens databases created before this fix.
    "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)",
)


def ensure_version_table_width(connection) -> None:
    for statement in _ENSURE_VERSION_TABLE_WIDTH:
        connection.execute(sa.text(statement))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        # NOTE: offline (--sql) output still contains Alembic's own
        # `CREATE TABLE alembic_version (version_num VARCHAR(32))`. Emitting the
        # widening DDL here too would just produce a duplicate CREATE TABLE in
        # the script, so it is left out; if you ever generate SQL offline for a
        # fresh database, widen version_num by hand before applying it.
        context.run_migrations()


def do_run_migrations(connection) -> None:
    ensure_version_table_width(connection)
    # Commit the DDL in its own transaction. Under SQLAlchemy 2.0 the executes
    # above implicitly opened one, and Alembic's context.begin_transaction()
    # is a no-op when a transaction is already active -- leaving it open makes
    # the entire migration run roll back on close while still logging success.
    connection.commit()
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = create_async_engine(settings.DATABASE_URL)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
