"""Run one validated FLUKE experiment in this process, outside the API."""

import argparse
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from fluke_backend.runner import RoundResults, RunConfig, build_fluke_config, write_result


def execute(run: RunConfig, data_dir: Path) -> RoundResults:
    """Use FLUKE's public construction, observer, and run APIs."""

    import torch
    from fluke import FlukeENV
    from fluke.algorithms.fedavg import FedAVG
    from fluke.algorithms.fedprox import FedProx
    from fluke.config import Configuration
    from fluke.data import DataSplitter
    from fluke.data.datasets import Datasets
    from fluke.evaluation import ClassificationEval
    from fluke.utils import FederationObserver, ServerObserver
    from fluke.utils.log import Log

    torch.set_num_threads(2)
    cfg = Configuration.from_dict(build_fluke_config(run, data_dir))
    FlukeENV().configure(cfg)
    data = Datasets.get(**cfg.data.dataset)
    FlukeENV().set_evaluator(ClassificationEval(eval_every=1, n_classes=data.num_classes))
    splitter = DataSplitter(
        dataset=data,
        distribution=cfg.data.distribution.name,
        dist_args=cfg.data.distribution.exclude("name"),
        **cfg.data.exclude("dataset", "distribution"),
    )
    algorithm_class = FedAVG if run.algorithm == "fedavg" else FedProx
    algorithm = algorithm_class(run.n_clients, splitter, cfg.method.hyperparameters)
    logger = Log()
    logger.init(**cfg, exp_id=algorithm.id)
    FlukeENV().set_logger(logger)

    class AccuracyObserver(RoundResults, ServerObserver, FederationObserver):
        pass

    accuracy = AccuracyObserver(run.algorithm, run.n_rounds)
    algorithm.set_callbacks([logger, accuracy])
    algorithm.run(run.n_rounds, cfg.protocol.eligible_perc)
    return accuracy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one fixed MNIST FLUKE experiment")
    parser.add_argument("config", type=Path, help="JSON file with the small experiment snapshot")
    parser.add_argument("output_dir", type=Path, help="server-owned output directory")
    parser.add_argument("data_dir", type=Path, help="server-owned MNIST dataset directory")
    args = parser.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    result_path = args.output_dir / "result.json"
    result_path.unlink(missing_ok=True)
    with (args.output_dir / "run.log").open("w", encoding="utf-8") as log:
        with redirect_stdout(log), redirect_stderr(log):
            try:
                run = RunConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
                print(f"Starting {run.algorithm}: {run.n_rounds} rounds, {run.n_clients} clients")
                accuracy = execute(run, args.data_dir)
                write_result(result_path, accuracy.validated_result())
                print("Training completed and result.json was written")
                return 0
            except Exception as exc:
                print(f"Runner failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                traceback.print_exc()
                return 1


if __name__ == "__main__":
    raise SystemExit(main())
