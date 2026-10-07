"""The runner's small input and result contracts work without FLUKE installed."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from fluke_backend.runner import RoundResults, RunConfig, build_fluke_config, write_result


def test_fedavg_snapshot_maps_to_fixed_cpu_mnist_configuration():
    request = RunConfig.model_validate({"algorithm": "fedavg"})

    assert request.n_clients == 4
    assert request.n_rounds == 2
    assert request.local_epochs == 1
    assert request.mu is None

    config = build_fluke_config(request, Path("/server/mnist"))
    assert config["data"]["dataset"] == {"name": "mnist", "path": "/server/mnist"}
    assert config["data"]["distribution"] == {"name": "iid"}
    assert config["data"]["sampling_perc"] == 0.01
    assert config["exp"] == {"device": "cpu", "seed": 42, "inmemory": True}
    assert config["protocol"] == {"eligible_perc": 1.0, "n_clients": 4, "n_rounds": 2}
    assert config["method"]["name"] == "fluke.algorithms.fedavg.FedAVG"
    assert config["method"]["hyperparameters"]["model"] == "MNIST_2NN"
    assert "mu" not in config["method"]["hyperparameters"]["client"]


def test_fedprox_snapshot_maps_mu_and_epochs():
    request = RunConfig.model_validate(
        {"algorithm": "fedprox", "n_clients": 2, "n_rounds": 2, "local_epochs": 3}
    )

    config = build_fluke_config(request, Path("/server/mnist"))
    assert request.mu == 0.3
    assert config["method"]["name"] == "fluke.algorithms.fedprox.FedProx"
    assert config["method"]["hyperparameters"]["client"]["mu"] == 0.3
    assert config["method"]["hyperparameters"]["client"]["local_epochs"] == 3


@pytest.mark.parametrize(
    "snapshot",
    [
        {"algorithm": "other"},
        {"algorithm": "fedavg", "mu": 0.3},
        {"algorithm": "fedavg", "mu": None},
        {"algorithm": "fedprox", "mu": 0},
        {"algorithm": "fedprox", "mu": None},
        {"algorithm": "fedavg", "n_clients": 1},
        {"algorithm": "fedavg", "n_clients": 4.0},
        {"algorithm": "fedavg", "n_rounds": 6},
        {"algorithm": "fedavg", "local_epochs": 0},
        {"algorithm": "fedavg", "n_clients": True},
        {"algorithm": "fedprox", "mu": float("inf")},
        {"algorithm": "fedavg", "dataset": "other"},
        {"algorithm": "fedavg", "path": "/tmp/injected"},
    ],
)
def test_invalid_or_unowned_configuration_is_rejected(snapshot):
    with pytest.raises(ValidationError):
        RunConfig.model_validate(snapshot)


def test_only_completed_rounds_are_written_and_final_duplicate_is_ignored(tmp_path):
    results = RoundResults("fedavg", 2)
    results.server_evaluation(round=1, eval_type="global", evals={"accuracy": 0.25})
    results.end_round(round=1)
    results.server_evaluation(round=2, eval_type="global", evals={"accuracy": 0.5})
    results.end_round(round=2)
    results.server_evaluation(round=2, eval_type="global", evals={"accuracy": 0.9})
    results.finished(round=3)

    result_path = tmp_path / "result.json"
    write_result(result_path, results.validated_result())

    assert json.loads(result_path.read_text()) == {
        "algorithm": "fedavg",
        "rounds": [{"round": 1, "accuracy": 0.25}, {"round": 2, "accuracy": 0.5}],
    }


@pytest.mark.parametrize("accuracy", [float("nan"), float("inf"), -0.1, 1.1])
def test_nonfinite_or_out_of_range_accuracy_cannot_complete(accuracy):
    results = RoundResults("fedavg", 1)
    results.server_evaluation(round=1, eval_type="global", evals={"accuracy": accuracy})
    results.end_round(round=1)
    results.finished(round=2)

    with pytest.raises(ValueError, match="accuracy"):
        results.validated_result()


def test_short_run_and_interrupted_run_cannot_complete():
    short = RoundResults("fedavg", 2)
    short.server_evaluation(round=1, eval_type="global", evals={"accuracy": 0.4})
    short.end_round(round=1)
    short.finished(round=2)
    with pytest.raises(ValueError, match="requested rounds"):
        short.validated_result()

    interrupted = RoundResults("fedavg", 1)
    interrupted.server_evaluation(round=1, eval_type="global", evals={"accuracy": 0.4})
    interrupted.end_round(round=1)
    interrupted.interrupted()
    interrupted.finished(round=2)
    with pytest.raises(ValueError, match="interrupted"):
        interrupted.validated_result()


def test_invalid_snapshot_fails_in_subprocess_with_log_and_no_stale_result(tmp_path):
    snapshot = tmp_path / "config.json"
    snapshot.write_text('{"algorithm":"not-supported"}')
    output = tmp_path / "output"
    output.mkdir()
    (output / "result.json").write_text('{"stale": true}')

    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "fluke_backend.runner_cli",
            str(snapshot),
            str(output),
            str(tmp_path / "data"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode != 0
    assert not (output / "result.json").exists()
    assert "algorithm" in (output / "run.log").read_text()


@pytest.mark.runner
def test_execution_failure_exits_without_result_and_keeps_diagnostic_log(tmp_path):
    if importlib.util.find_spec("fluke") is None:
        pytest.skip("Install the optional runner extra to exercise FLUKE")

    snapshot = tmp_path / "config.json"
    snapshot.write_text('{"algorithm":"fedavg","n_clients":2,"n_rounds":2}')
    output = tmp_path / "output"
    not_a_directory = tmp_path / "not_a_directory"
    not_a_directory.write_text("deliberate dataset path error")

    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "fluke_backend.runner_cli",
            str(snapshot),
            str(output),
            str(not_a_directory),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode != 0
    assert not (output / "result.json").exists()
    assert "NotADirectoryError" in (output / "run.log").read_text()
