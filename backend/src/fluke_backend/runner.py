"""Small, FLUKE-free run contract and round-result collector."""

import json
import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunConfig(BaseModel):
    """The only experiment values the future worker passes to the runner."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    algorithm: Literal["fedavg", "fedprox"]
    n_clients: int = Field(default=4, ge=2, le=10, strict=True)
    n_rounds: int = Field(default=2, ge=1, le=5, strict=True)
    local_epochs: int = Field(default=1, ge=1, le=3, strict=True)
    mu: float | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="after")
    def validate_mu(self) -> "RunConfig":
        if self.algorithm == "fedavg" and "mu" in self.model_fields_set:
            raise ValueError("mu is only accepted for FedProx")
        if self.algorithm == "fedprox" and self.mu is None:
            if "mu" in self.model_fields_set:
                raise ValueError("mu must be positive for FedProx")
            self.mu = 0.3
        return self


def build_fluke_config(run: RunConfig, data_dir: Path) -> dict:
    """Map the small snapshot to fixed MNIST/IID/CPU FLUKE settings."""

    client = {
        "batch_size": 32,
        "local_epochs": run.local_epochs,
        "loss": "CrossEntropyLoss",
        "optimizer": {"lr": 0.01, "momentum": 0.9, "weight_decay": 0.0001},
        "scheduler": {"gamma": 1, "step_size": 1},
    }
    if run.algorithm == "fedprox":
        client["mu"] = run.mu

    return {
        "data": {
            "dataset": {"name": "mnist", "path": str(data_dir)},
            "distribution": {"name": "iid"},
            "sampling_perc": 0.01,
            "client_split": 0.1,
            "keep_test": True,
            "server_test": True,
            "server_split": 0.0,
            "uniform_test": False,
        },
        "exp": {"device": "cpu", "seed": 42, "inmemory": True},
        "eval": {
            "task": "classification",
            "eval_every": 1,
            "pre_fit": False,
            "post_fit": False,
            "locals": False,
            "server": True,
        },
        "logger": {"name": "Log"},
        "protocol": {"eligible_perc": 1.0, "n_clients": run.n_clients, "n_rounds": run.n_rounds},
        "method": {
            "name": {
                "fedavg": "fluke.algorithms.fedavg.FedAVG",
                "fedprox": "fluke.algorithms.fedprox.FedProx",
            }[run.algorithm],
            "hyperparameters": {
                "client": client,
                "server": {"weighted": True},
                "model": "MNIST_2NN",
            },
        },
    }


class RoundResults:
    """Keep only evaluations for rounds FLUKE reports as finished."""

    def __init__(self, algorithm: str, requested_rounds: int):
        self.algorithm = algorithm
        self.requested_rounds = requested_rounds
        self._pending: dict[int, object] = {}
        self._rounds: list[dict] = []
        self._finished = False
        self._interrupted = False

    def server_evaluation(self, round: int, eval_type: str, evals: dict, **kwargs) -> None:
        if eval_type == "global" and round > len(self._rounds):
            self._pending[round] = evals.get("accuracy")

    def end_round(self, round: int) -> None:
        self._rounds.append({"round": round, "accuracy": self._pending.pop(round, None)})

    def interrupted(self) -> None:
        self._interrupted = True

    def early_stop(self, round: int) -> None:
        self._interrupted = True

    def finished(self, round: int) -> None:
        self._finished = True

    def validated_result(self) -> dict:
        if self._interrupted:
            raise ValueError("training was interrupted")
        if not self._finished or [item["round"] for item in self._rounds] != list(
            range(1, self.requested_rounds + 1)
        ):
            raise ValueError("training did not finish all requested rounds")
        for item in self._rounds:
            accuracy = item["accuracy"]
            if (
                isinstance(accuracy, bool)
                or not isinstance(accuracy, (float, int))
                or not math.isfinite(accuracy)
                or not 0 <= accuracy <= 1
            ):
                raise ValueError(f"round {item['round']} has invalid global accuracy")
        return {"algorithm": self.algorithm, "rounds": self._rounds}


def write_result(path: Path, result: dict) -> None:
    """Publish a complete result in one rename after training succeeds."""

    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(result, allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
