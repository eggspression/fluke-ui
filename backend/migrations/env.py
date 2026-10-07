"""Alembic migration environment; test URL is supplied only by disposable fixtures."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool

import fluke_backend.auth.models  # noqa: F401 - registers identity tables with Base.metadata
from fluke_backend.database import Base
from fluke_backend.settings import Settings

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> URL:
    supplied = config.attributes.get("connection_url")
    if supplied is not None:
        return make_url(supplied).set(drivername="postgresql+psycopg")
    return make_url(Settings().database_url.get_secret_value()).set(drivername="postgresql+psycopg")


def run_migrations_offline() -> None:
    context.configure(
        url=database_url().render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
