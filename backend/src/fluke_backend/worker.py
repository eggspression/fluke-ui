"""Run one queued FLUKE job at a time outside HTTP requests."""

import json
import math
import os
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from fluke_backend.database import Database
from fluke_backend.experiments.models import Run
from fluke_backend.settings import Settings


def _validated_result(path: Path, config: dict) -> dict:
    def reject_constant(value: str):
        raise ValueError(f"nonfinite value: {value}")

    result = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    if not isinstance(result, dict) or result.get("algorithm") != config["algorithm"]:
        raise ValueError("wrong result algorithm")
    rounds = result.get("rounds")
    if not isinstance(rounds, list) or len(rounds) != config["n_rounds"]:
        raise ValueError("incomplete result rounds")
    for expected_round, item in enumerate(rounds, 1):
        if not isinstance(item, dict) or item.get("round") != expected_round:
            raise ValueError("invalid result round order")
        accuracy = item.get("accuracy")
        if (
            isinstance(accuracy, bool)
            or not isinstance(accuracy, (int, float))
            or not math.isfinite(accuracy)
            or not 0 <= accuracy <= 1
        ):
            raise ValueError("invalid result accuracy")
    return {"algorithm": result["algorithm"], "rounds": rounds}


class Worker:
    def __init__(
        self,
        database: Database,
        artifacts_dir: Path,
        invoke: Callable = subprocess.run,
    ) -> None:
        self.database = database
        self.artifacts_dir = artifacts_dir
        self.invoke = invoke

    def check_startup(self) -> None:
        with self.database.transaction() as session:
            running = session.scalar(select(Run.id).where(Run.status == "RUNNING").limit(1))
        if running is not None:
            raise RuntimeError(f"unresolved RUNNING run {running}; inspect it before restarting")

    def process_one(self) -> bool:
        with self.database.transaction() as session:
            run = session.scalar(
                select(Run)
                .where(Run.status == "QUEUED")
                .order_by(Run.created_at, Run.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if run is None:
                return False
            run.status = "RUNNING"
            run.started_at = datetime.now(UTC)
            run_id = run.id
            config = dict(run.config)

        output_dir = self.artifacts_dir / "runs" / str(run_id)
        result_path = output_dir / "result.json"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            result_path.unlink(missing_ok=True)
            config_path = output_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            command = [
                sys.executable,
                "-m",
                "fluke_backend.runner_cli",
                str(config_path),
                str(output_dir),
                str(self.artifacts_dir / "mnist"),
            ]
            env = {key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR") if key in os.environ}
            env["PYTHONUNBUFFERED"] = "1"
            completed = self.invoke(command, env=env, capture_output=True, text=True)
            if completed.stdout or completed.stderr:
                with (output_dir / "run.log").open("a", encoding="utf-8") as log:
                    log.write(completed.stdout)
                    log.write(completed.stderr)
            if completed.returncode != 0:
                raise ValueError(f"Runner exited with code {completed.returncode}")
            result = _validated_result(result_path, config)
            status, message = "COMPLETED", None
        except Exception as exc:
            result = None
            status = "FAILED"
            message = (
                "Worker I/O error while preparing or running job"
                if isinstance(exc, OSError)
                else str(exc)
            )
            try:
                with (output_dir / "run.log").open("a", encoding="utf-8") as log:
                    log.write(f"\nWorker: {message}\n")
            except OSError:
                # The artifact directory may be the reason the run failed.
                pass

        with self.database.transaction() as session:
            run = session.get(Run, run_id)
            run.status = status
            run.result = result
            run.failure_message = message[:255] if message else None
            run.finished_at = datetime.now(UTC)
        return True

    def run_forever(self) -> None:
        self.check_startup()
        while True:
            if not self.process_one():
                time.sleep(2)


def main() -> int:
    settings = Settings()
    database = Database(settings)
    try:
        Worker(database, settings.artifacts_dir).run_forever()
    except KeyboardInterrupt:
        return 0
    except RuntimeError as exc:
        print(f"Worker stopped: {exc}", file=sys.stderr)
        return 1
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
