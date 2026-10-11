"""Single local worker behavior against disposable PostgreSQL."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import select

from fluke_backend.auth.accounts import AccountService
from fluke_backend.database import Database
from fluke_backend.experiments.models import Experiment, Run
from fluke_backend.settings import Settings

pytestmark = pytest.mark.postgres


@pytest.fixture
def queued(disposable_database, alembic_config, monkeypatch, tmp_path):
    command.upgrade(alembic_config, "head")
    monkeypatch.setenv("FLUKE_DATABASE_URL", disposable_database.url.render_as_string(False))
    database = Database(Settings())
    owner = AccountService(database).create_user("worker@example.com", "worker password")
    config = {"algorithm": "fedavg", "n_clients": 2, "n_rounds": 2, "local_epochs": 1}
    with database.transaction() as session:
        experiment = Experiment(owner_id=owner.id, name="Worker proof", config=config)
        session.add(experiment)
        session.flush()
        first = Run(
            owner_id=owner.id,
            experiment_id=experiment.id,
            config=config,
            created_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        second = Run(
            owner_id=owner.id,
            experiment_id=experiment.id,
            config=config,
            created_at=datetime.now(UTC),
        )
        session.add_all([first, second])
        session.flush()
        ids = first.id, second.id
    try:
        yield database, tmp_path / "artifacts", ids
    finally:
        database.close()


def test_worker_completes_oldest_run_with_valid_rounds(queued):
    from fluke_backend.worker import Worker

    database, artifacts, (first_id, second_id) = queued

    def fake_runner(command, *, env, capture_output, text):
        assert "FLUKE_DATABASE_URL" not in env
        assert "FLUKE_JWT_SECRET" not in env
        output = Path(command[-2])
        assert json.loads(Path(command[-3]).read_text())["n_rounds"] == 2
        assert output.name == str(first_id)
        (output / "result.json").write_text(
            json.dumps(
                {
                    "algorithm": "fedavg",
                    "rounds": [{"round": 1, "accuracy": 0.25}, {"round": 2, "accuracy": 0.5}],
                }
            )
        )
        (output / "run.log").write_text("Training completed\n")
        return type("Exit", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    worker = Worker(database, artifacts, invoke=fake_runner)
    assert worker.process_one() is True
    with database.transaction() as session:
        first = session.get(Run, first_id)
        second = session.get(Run, second_id)
        assert first.status == "COMPLETED"
        assert first.result["rounds"][1] == {"round": 2, "accuracy": 0.5}
        assert first.started_at is not None and first.finished_at is not None
        assert second.status == "QUEUED"


@pytest.mark.parametrize(
    "exit_code,rounds",
    [
        (1, [{"round": 1, "accuracy": 0.2}, {"round": 2, "accuracy": 0.4}]),
        (0, [{"round": 1, "accuracy": 0.2}]),
        (0, [{"round": 1, "accuracy": 0.2}, {"round": 2, "accuracy": float("nan")}]),
    ],
)
def test_worker_marks_failure_without_publishing_accuracy(queued, exit_code, rounds):
    from fluke_backend.worker import Worker

    database, artifacts, (first_id, _second_id) = queued

    def fake_runner(command, *, env, capture_output, text):
        output = Path(command[-2])
        (output / "run.log").write_text("Runner failed\n")
        (output / "result.json").write_text(json.dumps({"algorithm": "fedavg", "rounds": rounds}))
        return type("Exit", (), {"returncode": exit_code, "stdout": "", "stderr": ""})()

    assert Worker(database, artifacts, invoke=fake_runner).process_one() is True
    with database.transaction() as session:
        run = session.get(Run, first_id)
        assert run.status == "FAILED"
        assert run.result is None
        assert run.failure_message
        assert run.finished_at is not None


def test_worker_marks_failure_when_artifact_directory_cannot_be_created(queued):
    from fluke_backend.worker import Worker

    database, artifacts, (first_id, second_id) = queued
    artifacts.write_text("occupies the artifact directory")

    assert Worker(database, artifacts).process_one() is True
    with database.transaction() as session:
        first = session.get(Run, first_id)
        second = session.get(Run, second_id)
        assert first.status == "FAILED"
        assert first.result is None
        assert first.failure_message
        assert first.finished_at is not None
        assert second.status == "QUEUED"


def test_worker_refuses_unresolved_running_run(queued):
    from fluke_backend.worker import Worker

    database, artifacts, (first_id, _second_id) = queued
    with database.transaction() as session:
        session.get(Run, first_id).status = "RUNNING"
    with pytest.raises(RuntimeError, match="unresolved RUNNING"):
        Worker(database, artifacts).check_startup()
    with database.transaction() as session:
        assert session.scalar(select(Run.status).where(Run.id == first_id)) == "RUNNING"


def test_fresh_worker_process_can_claim_run(queued):
    database, artifacts, (first_id, _second_id) = queued
    script = """
import sys
from pathlib import Path
from fluke_backend.database import Database
from fluke_backend.settings import Settings
from fluke_backend.worker import Worker

class FailedRunner:
    returncode = 1
    stdout = ''
    stderr = ''

database = Database(Settings())
try:
    assert Worker(database, Path(sys.argv[1]), invoke=lambda *a, **k: FailedRunner()).process_one()
finally:
    database.close()
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(artifacts)], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    with database.transaction() as session:
        assert session.get(Run, first_id).status == "FAILED"


@pytest.mark.runner
def test_worker_completes_real_fluke_run(queued):
    from fluke_backend.worker import Worker

    cache = os.environ.get("TEST_MNIST_DIR")
    if not cache:
        pytest.skip("Set TEST_MNIST_DIR to a prepared MNIST cache")
    database, artifacts, (first_id, _second_id) = queued
    artifacts.mkdir()
    (artifacts / "mnist").symlink_to(Path(cache).resolve(), target_is_directory=True)
    assert Worker(database, artifacts).process_one() is True
    with database.transaction() as session:
        run = session.get(Run, first_id)
        assert run.status == "COMPLETED", run.failure_message
        assert [item["round"] for item in run.result["rounds"]] == [1, 2]
    assert (artifacts / "runs" / str(first_id) / "run.log").exists()


@pytest.mark.runner
def test_real_runner_failure_keeps_log_and_marks_failed(queued):
    from fluke_backend.worker import Worker

    database, artifacts, (first_id, _second_id) = queued
    artifacts.mkdir()
    (artifacts / "mnist").write_text("not a directory")
    assert Worker(database, artifacts).process_one() is True
    with database.transaction() as session:
        run = session.get(Run, first_id)
        assert run.status == "FAILED"
        assert run.result is None
        assert run.failure_message
    output = artifacts / "runs" / str(first_id)
    assert "Runner failed" in (output / "run.log").read_text()
    assert not (output / "result.json").exists()
