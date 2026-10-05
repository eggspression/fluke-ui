import os

import pytest


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    """Never read a developer's .env or deployment configuration in unit tests."""
    monkeypatch.chdir(tmp_path)
    for name in os.environ:
        if name.startswith("FLUKE_"):
            monkeypatch.delenv(name)
