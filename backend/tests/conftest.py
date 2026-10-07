import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic.config import Config
from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from tests.postgres_support import validate_admin_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    """Never read a developer's .env or deployment configuration in unit tests."""
    monkeypatch.chdir(tmp_path)
    for name in os.environ:
        if name.startswith("FLUKE_") and name != "FLUKE_TEST_ADMIN_URL":
            monkeypatch.delenv(name)
    monkeypatch.setenv("FLUKE_JWT_SECRET", "test-signing-secret-with-at-least-32-characters")


@pytest.fixture
def disposable_database():
    local_env = dotenv_values(BACKEND_ROOT / ".env")
    admin_url = os.environ.get("FLUKE_TEST_ADMIN_URL") or local_env.get("FLUKE_TEST_ADMIN_URL")
    if not admin_url:
        pytest.skip("Set FLUKE_TEST_ADMIN_URL to a local PostgreSQL maintenance URL")
    validate_admin_url(admin_url, local_env.get("FLUKE_DATABASE_URL"))
    name = f"fluke_test_{uuid4().hex}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        url = make_url(admin_url).set(drivername="postgresql+psycopg", database=name)
        engine = create_engine(url)
        try:
            yield engine
        finally:
            engine.dispose()
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def alembic_config(disposable_database):
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["connection_url"] = disposable_database.url
    return config
