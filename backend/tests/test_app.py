import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from fluke_backend.app import create_app


def test_liveness_works_without_database(monkeypatch):
    monkeypatch.setenv("FLUKE_DATABASE_URL", "postgresql://localhost:1/unavailable")
    with TestClient(create_app()) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_unavailable_database_without_exposing_credentials(monkeypatch):
    monkeypatch.setenv(
        "FLUKE_DATABASE_URL", "postgresql://user:private-password@127.0.0.1:1/unavailable"
    )
    with TestClient(create_app()) as client:
        response = client.get("/health/ready")
        liveness = client.get("/health/live")
    assert response.status_code == 503
    assert "private-password" not in response.text
    assert liveness.status_code == 200


def test_startup_rejects_missing_settings():
    with pytest.raises(ValidationError, match="database_url"):
        create_app()


def test_import_and_liveness_do_not_connect_or_load_training_libraries():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib.abc
import sys

class BoundaryGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'fluke', 'torch'}:
            raise AssertionError(f'Forbidden dependency: {fullname}')

sys.meta_path.insert(0, BoundaryGuard())
import psycopg
def forbidden_connection(*args, **kwargs):
    raise AssertionError('Database connection during import or liveness')
psycopg.connect = forbidden_connection
from fluke_backend.app import create_app
# Import must succeed before any configuration is supplied.
import os
os.environ['FLUKE_DATABASE_URL'] = 'postgresql://localhost:1/unavailable'
from fastapi.testclient import TestClient
with TestClient(create_app()) as client:
    assert client.get('/health/live').json() == {'status': 'ok'}
""",
        ],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
