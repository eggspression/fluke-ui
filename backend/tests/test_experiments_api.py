"""Owned experiment and queued-run API against disposable PostgreSQL."""

from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import select

from fluke_backend.app import create_app
from fluke_backend.auth.accounts import AccountService
from fluke_backend.database import Database
from fluke_backend.settings import Settings

pytestmark = pytest.mark.postgres


@pytest.fixture
def api(disposable_database, alembic_config, monkeypatch):
    command.upgrade(alembic_config, "head")
    monkeypatch.setenv("FLUKE_DATABASE_URL", disposable_database.url.render_as_string(False))
    database = Database(Settings())
    accounts = AccountService(database)
    accounts.create_user("alice@example.com", "alice password")
    accounts.create_user("bob@example.com", "bob password")
    try:
        with TestClient(create_app()) as client:
            tokens = {
                email: client.post(
                    "/api/v1/auth/login",
                    json={"email": f"{email}@example.com", "password": f"{email} password"},
                ).json()["access_token"]
                for email in ("alice", "bob")
            }
            yield client, database, tokens
    finally:
        database.close()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def form(**changes):
    return {"name": "First proof", "algorithm": "fedavg", **changes}


def test_create_list_get_and_edit_experiment(api):
    client, _database, tokens = api
    headers = auth(tokens["alice"])
    created = client.post("/api/v1/experiments", headers=headers, json=form())
    assert created.status_code == 201, created.text
    experiment = created.json()
    assert experiment["name"] == "First proof"
    assert experiment["config"] == {
        "algorithm": "fedavg",
        "n_clients": 4,
        "n_rounds": 2,
        "local_epochs": 1,
    }
    assert experiment["created_at"] and experiment["updated_at"]
    identifier = experiment["id"]
    assert client.get("/api/v1/experiments", headers=headers).json() == [experiment]
    assert client.get(f"/api/v1/experiments/{identifier}", headers=headers).json() == experiment

    changed = client.patch(
        f"/api/v1/experiments/{identifier}",
        headers=headers,
        json=form(name="Prox proof", algorithm="fedprox", mu=0.5, n_rounds=3),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["config"]["mu"] == 0.5
    assert changed.json()["config"]["n_rounds"] == 3
    assert client.get(f"/api/v1/experiments/{identifier}", headers=headers).json() == changed.json()


def test_run_launch_is_queued_snapshot_and_freezes_experiment(api):
    client, database, tokens = api
    headers = auth(tokens["alice"])
    experiment = client.post(
        "/api/v1/experiments", headers=headers, json=form(algorithm="fedprox")
    ).json()
    identifier = experiment["id"]
    launched = client.post(f"/api/v1/experiments/{identifier}/runs", headers=headers)
    assert launched.status_code == 202, launched.text
    run = launched.json()
    assert run["experiment_id"] == identifier
    assert run["status"] == "QUEUED"
    assert run["config"] == experiment["config"]
    assert run["failure_message"] is None
    assert run["created_at"] and run["updated_at"]
    assert client.get(f"/api/v1/runs/{run['id']}", headers=headers).json() == run
    assert client.get(f"/api/v1/experiments/{identifier}/runs", headers=headers).json() == [run]
    assert (
        client.patch(f"/api/v1/experiments/{identifier}", headers=headers, json=form()).status_code
        == 409
    )
    assert (
        client.get(f"/api/v1/runs/{run['id']}", headers=headers).json()["config"] == run["config"]
    )

    from fluke_backend.experiments.models import Experiment, Run

    with database.transaction() as session:
        stored = session.scalar(select(Run).where(Run.id == run["id"]))
        assert stored.config == run["config"]
        assert stored.status == "QUEUED"
        saved_experiment = session.scalar(select(Experiment).where(Experiment.id == identifier))
        assert saved_experiment.config == experiment["config"]
        saved_experiment.config = {"algorithm": "fedavg", "n_clients": 2}
    assert (
        client.get(f"/api/v1/runs/{run['id']}", headers=headers).json()["config"] == run["config"]
    )


def test_invalid_form_uses_fastapi_validation_errors(api):
    client, _database, tokens = api
    headers = auth(tokens["alice"])
    invalid = (
        form(name="   "),
        form(algorithm="other"),
        form(n_clients=1),
        form(n_clients=2.5),
        form(n_rounds=6),
        form(local_epochs=0),
        form(mu=0.3),
        form(algorithm="fedprox", mu=0),
        form(algorithm="fedprox", mu=None),
        form(dataset="private/path"),
    )
    for payload in invalid:
        response = client.post("/api/v1/experiments", headers=headers, json=payload)
        assert response.status_code == 422, (payload, response.text)
        assert isinstance(response.json()["detail"], list)
    assert client.get("/api/v1/experiments", headers=headers).json() == []


def test_owner_isolation_and_missing_ids(api):
    client, _database, tokens = api
    alice = auth(tokens["alice"])
    bob = auth(tokens["bob"])
    experiment = client.post("/api/v1/experiments", headers=alice, json=form()).json()
    identifier = experiment["id"]
    run = client.post(f"/api/v1/experiments/{identifier}/runs", headers=alice).json()
    assert client.get("/api/v1/experiments", headers=bob).json() == []
    for headers in (bob, alice):
        target = identifier if headers == bob else str(uuid4())
        assert client.get(f"/api/v1/experiments/{target}", headers=headers).status_code == 404
        assert (
            client.patch(f"/api/v1/experiments/{target}", headers=headers, json=form()).status_code
            == 404
        )
        assert client.post(f"/api/v1/experiments/{target}/runs", headers=headers).status_code == 404
        assert client.get(f"/api/v1/experiments/{target}/runs", headers=headers).status_code == 404
    assert client.get(f"/api/v1/runs/{run['id']}", headers=bob).status_code == 404
    assert client.get(f"/api/v1/runs/{uuid4()}", headers=alice).status_code == 404
    assert client.get("/api/v1/experiments").status_code == 401
    assert client.post("/api/v1/experiments", json=form()).status_code == 401
