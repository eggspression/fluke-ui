"""Guardrails for disposable PostgreSQL integration databases."""

from sqlalchemy.engine import make_url


def validate_admin_url(admin_url: str, app_url: str | None) -> None:
    admin = make_url(admin_url)
    loopback_hosts = {"localhost", "127.0.0.1", "::1"}
    if admin.drivername != "postgresql" or admin.host not in loopback_hosts:
        raise ValueError("Test administration requires a local PostgreSQL URL")
    if admin.database != "postgres":
        raise ValueError("Test administration must connect to the postgres maintenance database")
    if admin.query:
        raise ValueError("Test administration URL must not contain connection query parameters")
    if app_url:
        app = make_url(app_url)
        if (
            app.host in loopback_hosts
            and (admin.port or 5432) == (app.port or 5432)
            and admin.database == app.database
        ):
            raise ValueError("Test administration URL must differ from the application database")
