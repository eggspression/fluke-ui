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


def test_startup_rejects_missing_settings():
    with pytest.raises(ValidationError, match="database_url"):
        create_app()


def test_import_and_liveness_do_not_load_training_or_database_libraries():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib.abc
import sys

class BoundaryGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'fluke', 'torch', 'sqlalchemy', 'psycopg'}:
            raise AssertionError(f'Forbidden dependency: {fullname}')

sys.meta_path.insert(0, BoundaryGuard())
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
