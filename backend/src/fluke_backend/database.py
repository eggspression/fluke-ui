"""PostgreSQL connection and transactional session lifecycle."""

from contextlib import AbstractContextManager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from fluke_backend.settings import Settings

EXPECTED_REVISION = "20261007_0002"


class Base(DeclarativeBase):
    """Shared metadata for application tables; only Alembic changes the schema."""


class Database:
    def __init__(self, settings: Settings) -> None:
        url = make_url(settings.database_url.get_secret_value()).set(
            drivername="postgresql+psycopg"
        )
        # Creating an engine does not open a connection or alter the schema.
        self.engine: Engine = create_engine(
            url, pool_pre_ping=True, connect_args={"connect_timeout": 2}
        )
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def transaction(self) -> AbstractContextManager[Session]:
        """Return a context manager that commits or rolls back and then closes."""
        return self._sessions.begin()

    def schema_is_current(self) -> bool:
        with self.engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        return revision == EXPECTED_REVISION

    def close(self) -> None:
        self.engine.dispose()
