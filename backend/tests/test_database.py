"""BE-02 integration checks: always run against a disposable PostgreSQL database."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text

from fluke_backend.app import create_app
from fluke_backend.auth.models import User
from fluke_backend.database import EXPECTED_REVISION, Database
from fluke_backend.settings import Settings

pytestmark = pytest.mark.postgres


def test_migrations_leave_expected_tables(disposable_database, alembic_config):
    command.upgrade(alembic_config, "head")
    inspector = inspect(disposable_database)
    assert set(inspector.get_table_names()) == {"users", "experiments", "runs", "alembic_version"}
    assert inspector.get_columns("users")[0]["name"] == "id"
    with disposable_database.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            EXPECTED_REVISION
        )
    command.check(alembic_config)


def test_migrations_downgrade_and_reapply(disposable_database, alembic_config):
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    assert "users" not in inspect(disposable_database).get_table_names()
    command.upgrade(alembic_config, "head")
    assert set(inspect(disposable_database).get_table_names()) == {
        "users",
        "experiments",
        "runs",
        "alembic_version",
    }


def test_session_removal_migration_preserves_existing_users(disposable_database, alembic_config):
    command.upgrade(alembic_config, "20261006_0001")
    with disposable_database.begin() as connection:
        connection.execute(
            text("INSERT INTO users (email, password_hash) VALUES ('existing@example.com', 'hash')")
        )
    command.upgrade(alembic_config, "head")
    with disposable_database.connect() as connection:
        assert (
            connection.execute(text("SELECT email FROM users")).scalar_one()
            == "existing@example.com"
        )
    assert "sessions" not in inspect(disposable_database).get_table_names()
    command.downgrade(alembic_config, "20261006_0001")
    assert "sessions" in inspect(disposable_database).get_table_names()


def test_transaction_commits_uuid_and_utc_timestamps(disposable_database, alembic_config):
    command.upgrade(alembic_config, "head")
    database = Database(Settings(database_url=disposable_database.url.render_as_string(False)))
    try:
        with database.transaction() as session:
            user = User(email="first@example.com", password_hash="not-a-real-hash")
            session.add(user)
            session.flush()
        with database.transaction() as session:
            stored = session.scalar(select(User).where(User.email == "first@example.com"))
            assert isinstance(stored.id, UUID)
            assert stored.created_at.tzinfo is not None
            assert abs((stored.created_at.astimezone(UTC) - datetime.now(UTC)).total_seconds()) < 5
    finally:
        database.close()


def test_failed_transaction_rolls_back_flushed_writes(disposable_database, alembic_config):
    command.upgrade(alembic_config, "head")
    database = Database(Settings(database_url=disposable_database.url.render_as_string(False)))
    try:
        with pytest.raises(RuntimeError, match="abort"):
            with database.transaction() as session:
                session.add(User(email="rollback@example.com", password_hash="not-a-real-hash"))
                session.flush()
                raise RuntimeError("abort")
        with database.transaction() as session:
            assert session.scalar(select(User).where(User.email == "rollback@example.com")) is None
    finally:
        database.close()


def test_readiness_requires_current_migration(disposable_database, alembic_config, monkeypatch):
    monkeypatch.setenv("FLUKE_DATABASE_URL", disposable_database.url.render_as_string(False))
    with TestClient(create_app()) as client:
        assert client.get("/health/ready").status_code == 503
        assert client.get("/health/live").status_code == 200
        command.upgrade(alembic_config, "head")
        assert client.get("/health/ready").json() == {"status": "ok"}
        with disposable_database.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = 'obsolete'"))
        assert client.get("/health/ready").status_code == 503
        assert client.get("/health/live").status_code == 200
