"""Authenticated experiment and queued-run endpoints."""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from fluke_backend.auth.api import get_current_user
from fluke_backend.auth.tokens import AuthenticatedUser
from fluke_backend.experiments.models import Experiment, Run
from fluke_backend.experiments.service import (
    ExperimentLocked,
    ExperimentService,
    ResourceNotFound,
)
from fluke_backend.runner import RunConfig

router = APIRouter(prefix="/api/v1", tags=["experiments"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


class ExperimentForm(RunConfig):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("name cannot be empty")
        return name

    def run_config(self) -> dict:
        return self.model_dump(exclude={"name"}, exclude_none=True)


class ExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    config: dict
    created_at: datetime
    updated_at: datetime


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    experiment_id: UUID
    config: dict
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
    result: dict | None
    failure_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


def _service(request: Request) -> ExperimentService:
    return ExperimentService(request.app.state.database)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not Found")


def _experiment(row: Experiment) -> ExperimentResponse:
    return ExperimentResponse.model_validate(row)


def _run(row: Run) -> RunResponse:
    return RunResponse.model_validate(row)


@router.post("/experiments", response_model=ExperimentResponse, status_code=201)
def create_experiment(
    request: Request, form: ExperimentForm, user: CurrentUser
) -> ExperimentResponse:
    return _experiment(_service(request).create(user.id, form.name, form.run_config()))


@router.get("/experiments", response_model=list[ExperimentResponse])
def list_experiments(request: Request, user: CurrentUser) -> list[ExperimentResponse]:
    return [_experiment(row) for row in _service(request).list(user.id)]


@router.get("/experiments/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(request: Request, experiment_id: UUID, user: CurrentUser) -> ExperimentResponse:
    try:
        return _experiment(_service(request).get(user.id, experiment_id))
    except ResourceNotFound:
        raise _not_found() from None


@router.patch("/experiments/{experiment_id}", response_model=ExperimentResponse)
def edit_experiment(
    request: Request, experiment_id: UUID, form: ExperimentForm, user: CurrentUser
) -> ExperimentResponse:
    try:
        return _experiment(
            _service(request).edit(user.id, experiment_id, form.name, form.run_config())
        )
    except ResourceNotFound:
        raise _not_found() from None
    except ExperimentLocked:
        raise HTTPException(status_code=409, detail="Experiment already has runs") from None


@router.post("/experiments/{experiment_id}/runs", response_model=RunResponse, status_code=202)
def launch_run(request: Request, experiment_id: UUID, user: CurrentUser) -> RunResponse:
    try:
        return _run(_service(request).launch(user.id, experiment_id))
    except ResourceNotFound:
        raise _not_found() from None


@router.get("/experiments/{experiment_id}/runs", response_model=list[RunResponse])
def list_runs(request: Request, experiment_id: UUID, user: CurrentUser) -> list[RunResponse]:
    try:
        return [_run(row) for row in _service(request).history(user.id, experiment_id)]
    except ResourceNotFound:
        raise _not_found() from None


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(request: Request, run_id: UUID, user: CurrentUser) -> RunResponse:
    try:
        return _run(_service(request).get_run(user.id, run_id))
    except ResourceNotFound:
        raise _not_found() from None


class RunLogResponse(BaseModel):
    text: str


@router.get("/runs/{run_id}/logs", response_model=RunLogResponse)
def get_run_logs(request: Request, run_id: UUID, user: CurrentUser) -> RunLogResponse:
    try:
        _service(request).get_run(user.id, run_id)
    except ResourceNotFound:
        raise _not_found() from None
    log_path: Path = request.app.state.settings.artifacts_dir / "runs" / str(run_id) / "run.log"
    try:
        with log_path.open("rb") as log:
            log.seek(0, 2)
            log.seek(max(0, log.tell() - 65536))
            return RunLogResponse(text=log.read().decode("utf-8", errors="replace"))
    except FileNotFoundError:
        return RunLogResponse(text="")
