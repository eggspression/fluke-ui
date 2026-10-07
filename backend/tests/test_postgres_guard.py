import pytest
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from sqlalchemy.engine import make_url

from tests.postgres_support import validate_admin_url


@pytest.mark.parametrize(
    ("admin_url", "app_url"),
    [
        (
            "postgresql://user:password@localhost/fluke",
            "postgresql://user:password@localhost/fluke",
        ),
        (
            "postgresql://user:password@localhost/postgres",
            "postgresql://user:password@127.0.0.1:5432/postgres",
        ),
        ("postgresql://user:password@remote.example/postgres", None),
        ("postgresql://user:password@localhost/fluke_test", None),
        ("sqlite:///local.db", None),
        ("postgresql://user:password@localhost/postgres?dbname=fluke", None),
        ("postgresql://user:password@localhost/postgres?host=remote.example", None),
        ("postgresql://user:password@localhost/postgres?hostaddr=198.51.100.1", None),
        ("postgresql://user:password@localhost/postgres?service=unexpected", None),
    ],
)
def test_test_database_guard_rejects_unsafe_targets(admin_url, app_url):
    with pytest.raises(ValueError):
        validate_admin_url(admin_url, app_url)


def test_test_database_guard_accepts_local_maintenance_database():
    admin_url = "postgresql://user:password@127.0.0.1/postgres"
    validate_admin_url(
        admin_url,
        "postgresql://user:password@127.0.0.1/fluke",
    )
    target = make_url(admin_url).set(
        drivername="postgresql+psycopg", database="fluke_test_generated"
    )
    _, arguments = PGDialect_psycopg().create_connect_args(target)
    assert arguments["dbname"] == "fluke_test_generated"
    assert arguments["host"] == "127.0.0.1"
