"""Environment configuration, validated when the application is created."""

from urllib.parse import urlsplit

from pydantic import Field, PostgresDsn, SecretStr, TypeAdapter, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLUKE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: SecretStr
    jwt_secret: SecretStr
    development_origins: list[str] = Field(default_factory=list)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            TypeAdapter(PostgresDsn).validate_python(value.get_secret_value())
        except ValueError:
            raise ValueError("must be a valid PostgreSQL connection URL") from None
        return value

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("must be at least 32 characters")
        return value

    @field_validator("development_origins")
    @classmethod
    def validate_development_origins(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in value
            ):
                raise ValueError("must contain only explicit HTTP origins")
        return values
