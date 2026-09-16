import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from airtag_sentry.config import database_url_from_env

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
#
# disable_existing_loggers=False is required here: fileConfig()'s default of
# True disables every logger that already exists at this point and isn't
# explicitly listed in alembic.ini's [loggers] (root/sqlalchemy/alembic only)
# - and by the time this runs, every airtag_sentry.* module logger already
# exists, because migrate.upgrade_to_head() (which loads this file) is only
# ever called from cli.py *after* it has already imported tracker.py/
# web/app.py and everything they pull in. Without this, every application
# log line (this notifier included) silently disappears for the rest of the
# process's life the moment migrations run at startup - confirmed the hard
# way: a caplog-based test here passed locally (no DB, so this file's
# fileConfig() call never ran) and failed in CI (a real Postgres runs the
# full migration suite first), which is exactly this bug catching itself.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# No ORM models in this project (db.py is plain psycopg3) - Alembic is used
# purely for migration bookkeeping, so there's no metadata to autogenerate from.
target_metadata = None

# The DB URL comes from POSTGRES_* env vars (see README: "Database
# migrations"), the same derivation airtag_sentry.config uses - deliberately
# NOT load_config(), so running migrations doesn't require the rest of the
# app's config (GitHub OAuth, encryption key). TEST_DATABASE_URL (the same
# override tests/test_db.py already uses) takes precedence when set.
# SQLAlchemy needs the "+psycopg" dialect suffix for psycopg3; the app's own
# db.py connects with plain psycopg3 and doesn't use this suffix.
_database_url = os.environ.get("TEST_DATABASE_URL") or database_url_from_env()
config.set_main_option("sqlalchemy.url", _database_url.replace("postgresql://", "postgresql+psycopg://", 1))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
