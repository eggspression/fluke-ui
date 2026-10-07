import pytest
from pydantic import ValidationError

from fluke_backend.settings import Settings


def test_database_url_is_required():
    with pytest.raises(ValidationError, match="database_url"):
        Settings()


def test_signing_secret_is_required_and_validated(monkeypatch):
    monkeypatch.setenv("FLUKE_DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.delenv("FLUKE_JWT_SECRET")
    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings()
    monkeypatch.setenv("FLUKE_JWT_SECRET", "short")
    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings()


@pytest.mark.parametrize("url", ["", "invalid", "sqlite:///local.db", "postgresql://"])
def test_rejects_invalid_or_non_postgresql_database_url(monkeypatch, url):
    monkeypatch.setenv("FLUKE_DATABASE_URL", url)
    with pytest.raises(ValidationError, match="database_url"):
        Settings()


def test_environment_overrides_dotenv(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "FLUKE_DATABASE_URL=postgresql://localhost/from_file\nPOSTGRES_PASSWORD=unused\n"
    )
    monkeypatch.setenv("FLUKE_DATABASE_URL", "postgresql://localhost/from_environment")
    settings = Settings()
    assert settings.database_url.get_secret_value() == "postgresql://localhost/from_environment"


def test_loads_local_dotenv(tmp_path):
    (tmp_path / ".env").write_text("FLUKE_DATABASE_URL=postgresql://localhost/local\n")
    assert Settings().database_url.get_secret_value() == "postgresql://localhost/local"


def test_database_credentials_are_hidden_in_repr_and_errors(monkeypatch):
    monkeypatch.setenv("FLUKE_DATABASE_URL", "postgresql://user:private-password@localhost/db")
    assert "private-password" not in repr(Settings())
    monkeypatch.setenv("FLUKE_DATABASE_URL", "mysql://user:private-password@localhost/db")
    with pytest.raises(ValidationError) as error:
        Settings()
    assert "private-password" not in str(error.value)
