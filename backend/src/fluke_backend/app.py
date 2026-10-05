"""FastAPI application factory; importing this module has no runtime side effects."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from fluke_backend.settings import Settings


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


def create_app() -> FastAPI:
    app = FastAPI(title="FLUKE Backend", version="0.1.0")
    app.state.settings = Settings()

    @app.get("/health/live", response_model=LivenessResponse, tags=["health"])
    def liveness() -> LivenessResponse:
        """Confirm the API is alive, independently of PostgreSQL and the runner."""
        return LivenessResponse()

    return app
