# FLUKE backend

BE-01 provides an installable API package, environment validation, and
`GET /health/live`. Database access/migrations begin in BE-02; authentication,
worker execution, and training are later tickets. Liveness is not readiness.

## Requirements

- uv (project/package management) and Python 3.11, installable using uv.
- Docker with the Compose v2 plugin for the PostgreSQL development service.
- Network access for the first Python, package, and container downloads.

## First setup

Run from `backend/`:

```sh
uv python install 3.11
uv sync --locked
cp .env.example .env
```

`uv.lock` records the resolved dependencies. Use `uv sync --locked` for repeatable
installs; regenerate the lock with `uv lock` only when intentionally changing
dependencies. Do not hand-edit the lockfile.

**Verification (2026-10-05):** Python 3.11.16 passes all 11 tests, Ruff lint and
format checks, and package builds. A fresh non-editable installation using an
empty cache also passes the suite and serves `/health/live` over real HTTP.
Starlette emits one upstream HTTPX deprecation warning; tests still pass.
PostgreSQL 17.11 is verified on Colima: health, password authentication, localhost
port forwarding, and named-volume persistence across container recreation all pass.

Generate a local password using `openssl rand -hex 24`. Put the result in
`POSTGRES_PASSWORD` in `.env`, and set `FLUKE_DATABASE_URL` to
`postgresql://fluke:<that-password>@127.0.0.1:5432/fluke`.
Keep `.env` private; it is ignored. Blank or invalid database URLs stop API
startup with a validation error naming `database_url`. Environment variables
override `.env`; importing the application does not read settings or connect.

```sh
docker compose up -d --wait postgres
uv run --locked uvicorn fluke_backend.app:create_app --factory --reload
```

Visit <http://127.0.0.1:8000/health/live> for `{"status":"ok"}` and
<http://127.0.0.1:8000/docs> for generated API documentation. Database availability
does not affect liveness. No tables are created by startup or import.

`docker compose down` stops the development database and retains its named volume.
The configured password initializes a new volume; changing `.env` does not change
the password of an existing database. The database port is bound to localhost.

### macOS with Colima

This development machine uses Colima with 2 CPUs, 2 GiB RAM, and a 20 GiB data disk.
To install the same tools on another Mac:

```sh
brew install colima docker docker-compose
colima start --cpus 2 --memory 2 --disk 20 --vm-type vz
```

Homebrew's Compose plugin needs Docker plugin discovery configured. Add the
directory reported by Homebrew to `cliPluginsExtraDirs` in `~/.docker/config.json`,
preserving any existing settings. On Apple Silicon Homebrew this is
`/opt/homebrew/lib/docker/cli-plugins`. Verify with `docker compose version`.
This configuration has already been applied on this machine.

After a reboot, run `colima start`, then `docker compose up -d --wait postgres`
from `backend/`. Use `colima stop` to stop the VM when finished; its database
volume remains on disk. Automatic startup at login has not been enabled.

## Checks

```sh
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
```

Tests use isolated settings and require neither PostgreSQL nor training packages.
There is no numeric coverage threshold yet; the BE-01 acceptance behaviors are
covered explicitly. Future transactional tests must use PostgreSQL, not SQLite.

Generate the tracked OpenAPI snapshot from the application factory:

```sh
FLUKE_DATABASE_URL=postgresql://localhost/schema uv run --locked python -c 'import json; from pathlib import Path; from fluke_backend.app import create_app; Path("openapi.json").write_text(json.dumps(create_app().openapi(), indent=2) + "\n")'
```

For a clean install check, use a new temporary environment without altering `.venv`:

```sh
smoke_dir=$(mktemp -d)
UV_PROJECT_ENVIRONMENT="$smoke_dir/venv" uv sync --locked --no-editable
UV_PROJECT_ENVIRONMENT="$smoke_dir/venv" uv run --locked --no-editable pytest
```

## Dependency boundaries

Base dependencies are FastAPI, Pydantic, Pydantic Settings, and Uvicorn. The `dev`
group adds pytest, HTTPX, and Ruff. The optional `runner` extra is reserved and
currently empty; BE-14 adds the pinned FLUKE stack. Installing it today adds no
training functionality. Neither the API nor its tests need FLUKE or PyTorch.
SQLAlchemy, Alembic, and the PostgreSQL driver will be added with BE-02.

Domain packages (`auth`, `catalog`, `experiments`, `runs`, `worker`, `runner`, and
`artifacts`) will be introduced with their owning tickets, with matching tests.

If uv's normal cache is unavailable in a restricted workspace, set
`UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` to writable, ignored local directories.
See the [uv project guide](https://docs.astral.sh/uv/guides/projects/) and
[Pydantic Settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).
