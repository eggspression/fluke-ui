"""HTTP authentication against disposable PostgreSQL databases."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from alembic import command
from fastapi.testclient import TestClient

from fluke_backend.app import create_app
from fluke_backend.auth import cli
from fluke_backend.auth.accounts import AccountService
from fluke_backend.database import Database
from fluke_backend.settings import Settings

pytestmark = pytest.mark.postgres
SECRET = "test-signing-secret-with-at-least-32-characters"


@pytest.fixture
def auth_setup(disposable_database, alembic_config, monkeypatch):
    command.upgrade(alembic_config, "head")
    monkeypatch.setenv("FLUKE_DATABASE_URL", disposable_database.url.render_as_string(False))
    monkeypatch.setenv("FLUKE_JWT_SECRET", SECRET)
    database = Database(Settings())
    accounts = AccountService(database)
    user = accounts.create_user("Member@Example.com", "correct secret phrase")
    try:
        yield accounts, user
    finally:
        database.close()


def login(client, password="correct secret phrase", email="member@example.com"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_issues_one_hour_user_token_without_server_session(auth_setup):
    _accounts, user = auth_setup
    with TestClient(create_app()) as client:
        response = login(client)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["user"] == {"id": str(user.id), "email": "member@example.com"}
        assert payload["token_type"] == "bearer"
        assert "correct secret phrase" not in response.text
        claims = jwt.decode(
            payload["access_token"], SECRET, algorithms=["HS256"], issuer="fluke-backend"
        )
        assert claims["sub"] == str(user.id)
        assert "sid" not in claims
        assert datetime.fromtimestamp(claims["exp"], UTC) - datetime.fromtimestamp(
            claims["iat"], UTC
        ) == timedelta(hours=1)
        assert (
            client.get("/api/v1/auth/me", headers=bearer(payload["access_token"])).json()
            == payload["user"]
        )
        assert (
            client.post("/api/v1/auth/logout", headers=bearer(payload["access_token"])).status_code
            == 404
        )


def test_bad_credentials_and_missing_token_are_generic(auth_setup):
    with TestClient(create_app()) as client:
        wrong_password = login(client, password="bad password")
        missing_user = login(client, email="other@example.com")
        no_token = client.get("/api/v1/auth/me")
        assert wrong_password.status_code == missing_user.status_code == no_token.status_code == 401
        assert wrong_password.json() == missing_user.json() == no_token.json()
        assert "bad password" not in wrong_password.text


def test_operator_provisioned_account_can_use_persistent_api(auth_setup, monkeypatch):
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "operator-created secret")
    assert cli.main(["create-user", "--email", "New@Example.com"]) == 0
    with TestClient(create_app()) as client:
        response = login(client, email="new@example.com", password="operator-created secret")
        assert response.status_code == 200
        token = response.json()["access_token"]
        assert (
            client.get("/api/v1/auth/me", headers=bearer(token)).json()["email"]
            == "new@example.com"
        )


def test_invalid_expired_and_forged_tokens_are_rejected(auth_setup):
    with TestClient(create_app()) as client:
        token = login(client).json()["access_token"]
        claims = jwt.decode(token, SECRET, algorithms=["HS256"], issuer="fluke-backend")
        invalid_tokens = (
            jwt.encode(claims, "another-signing-secret-long-enough-for-tests", algorithm="HS256"),
            jwt.encode(
                {**claims, "exp": datetime.now(UTC) - timedelta(seconds=1)},
                SECRET,
                algorithm="HS256",
            ),
            jwt.encode({**claims, "sub": str(uuid4())}, SECRET, algorithm="HS256"),
            jwt.encode({**claims, "sub": 123}, SECRET, algorithm="HS256"),
            jwt.encode({**claims, "sid": str(uuid4())}, SECRET, algorithm="HS256"),
            "not-a-jwt",
        )
        for invalid in invalid_tokens:
            assert client.get("/api/v1/auth/me", headers=bearer(invalid)).status_code == 401


def test_password_reset_keeps_issued_token_valid_but_deactivation_rejects_it(auth_setup):
    accounts, _user = auth_setup
    with TestClient(create_app()) as client:
        first = login(client).json()["access_token"]
        accounts.reset_password("member@example.com", "new secret phrase")
        assert client.get("/api/v1/auth/me", headers=bearer(first)).status_code == 200
        assert login(client).status_code == 401
        second = login(client, password="new secret phrase").json()["access_token"]
        accounts.deactivate_user("member@example.com")
        assert client.get("/api/v1/auth/me", headers=bearer(first)).status_code == 401
        assert client.get("/api/v1/auth/me", headers=bearer(second)).status_code == 401
        assert login(client, password="new secret phrase").status_code == 401


def test_fastapi_errors_cors_and_no_sensitive_logs(auth_setup, monkeypatch, caplog):
    monkeypatch.setenv("FLUKE_DEVELOPMENT_ORIGINS", '["http://localhost:4200"]')
    caplog.set_level(logging.DEBUG)
    with TestClient(create_app()) as client:
        invalid = client.post("/api/v1/auth/login", json={"email": "member@example.com"})
        assert invalid.status_code == 422
        assert isinstance(invalid.json()["detail"], list)
        assert client.get("/api/v1/absent").json() == {"detail": "Not Found"}
        token = login(client).json()["access_token"]
        assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 200
        preflight = client.options(
            "/api/v1/auth/login",
            headers={"Origin": "http://localhost:4200", "Access-Control-Request-Method": "POST"},
        )
        assert preflight.headers["Access-Control-Allow-Origin"] == "http://localhost:4200"
        rejected = client.options(
            "/api/v1/auth/login",
            headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
        )
        assert rejected.status_code == 400
        assert "Access-Control-Allow-Origin" not in rejected.headers
    assert "correct secret phrase" not in caplog.text
    assert token not in caplog.text
