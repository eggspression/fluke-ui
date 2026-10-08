"""Owned experiment changes and queued run creation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from fluke_backend.database import Database
from fluke_backend.experiments.models import Experiment, Run


class ResourceNotFound(Exception):
    pass


class ExperimentLocked(Exception):
    pass


class ExperimentService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, owner_id: UUID, name: str, config: dict) -> Experiment:
        with self.database.transaction() as session:
            experiment = Experiment(owner_id=owner_id, name=name, config=config)
            session.add(experiment)
            session.flush()
        return experiment

    def list(self, owner_id: UUID) -> list[Experiment]:
        with self.database.transaction() as session:
            return list(
                session.scalars(
                    select(Experiment)
                    .where(Experiment.owner_id == owner_id)
                    .order_by(Experiment.created_at.desc(), Experiment.id.desc())
                )
            )

    def get(self, owner_id: UUID, experiment_id: UUID) -> Experiment:
        with self.database.transaction() as session:
            experiment = session.scalar(
                select(Experiment).where(
                    Experiment.id == experiment_id, Experiment.owner_id == owner_id
                )
            )
            if experiment is None:
                raise ResourceNotFound
            return experiment

    def edit(self, owner_id: UUID, experiment_id: UUID, name: str, config: dict) -> Experiment:
        with self.database.transaction() as session:
            experiment = self._locked_experiment(session, owner_id, experiment_id)
            has_run = session.scalar(
                select(Run.id).where(Run.experiment_id == experiment_id).limit(1)
            )
            if has_run is not None:
                raise ExperimentLocked
            experiment.name = name
            experiment.config = config
            session.flush()
            session.refresh(experiment)
            return experiment

    def launch(self, owner_id: UUID, experiment_id: UUID) -> Run:
        with self.database.transaction() as session:
            experiment = self._locked_experiment(session, owner_id, experiment_id)
            run = Run(
                owner_id=owner_id,
                experiment_id=experiment.id,
                config=dict(experiment.config),
                status="QUEUED",
            )
            session.add(run)
            session.flush()
            return run

    def history(self, owner_id: UUID, experiment_id: UUID) -> list[Run]:
        with self.database.transaction() as session:
            self._owned_experiment(session, owner_id, experiment_id)
            return list(
                session.scalars(
                    select(Run)
                    .where(Run.owner_id == owner_id, Run.experiment_id == experiment_id)
                    .order_by(Run.created_at.desc(), Run.id.desc())
                )
            )

    def get_run(self, owner_id: UUID, run_id: UUID) -> Run:
        with self.database.transaction() as session:
            run = session.scalar(select(Run).where(Run.id == run_id, Run.owner_id == owner_id))
            if run is None:
                raise ResourceNotFound
            return run

    @staticmethod
    def _owned_experiment(session, owner_id: UUID, experiment_id: UUID) -> Experiment:
        experiment = session.scalar(
            select(Experiment).where(
                Experiment.id == experiment_id, Experiment.owner_id == owner_id
            )
        )
        if experiment is None:
            raise ResourceNotFound
        return experiment

    @classmethod
    def _locked_experiment(cls, session, owner_id: UUID, experiment_id: UUID) -> Experiment:
        experiment = session.scalar(
            select(Experiment)
            .where(Experiment.id == experiment_id, Experiment.owner_id == owner_id)
            .with_for_update()
        )
        if experiment is None:
            raise ResourceNotFound
        return experiment
