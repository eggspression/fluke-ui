"""FastAPI application factory; importing this module has no runtime side effects."""

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.cors import CORSMiddleware

from fluke_backend.auth.api import router as auth_router
from fluke_backend.database import Database
from fluke_backend.experiments.api import router as experiments_router
from fluke_backend.settings import Settings


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


def create_app() -> FastAPI:
    settings = Settings()
    database = Database(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            database.close()

    app = FastAPI(title="FLUKE Backend", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.database = database

    if settings.development_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.development_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(auth_router)
    app.include_router(experiments_router)

    @app.get("/health/live", response_model=LivenessResponse, tags=["health"])
    def liveness() -> LivenessResponse:
        """Confirm the API is alive, independently of PostgreSQL and the runner."""
        return LivenessResponse()

    @app.get(
        "/health/ready",
        response_model=LivenessResponse,
        responses={
            503: {
                "description": "Database unavailable or schema out of date",
            }
        },
        tags=["health"],
    )
    def readiness() -> LivenessResponse:
        """Only serve traffic when PostgreSQL has the expected migration."""
        try:
            if database.schema_is_current():
                return LivenessResponse()
        except SQLAlchemyError:
            pass
        raise HTTPException(status_code=503, detail="Database unavailable or schema is out of date")

    return app
