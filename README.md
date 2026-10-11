# FLUKE UI

FLUKE UI is a local web app for configuring and inspecting small federated learning experiments. A user signs in, saves a FedAvg or FedProx experiment, launches a CPU run, follows its status and recent log, and views global accuracy by round. [FLUKE](https://github.com/makgyver/fluke) performs the training; this project supplies the web interface, API, persistence, and local job worker.

The current MVP uses **MNIST**, IID data, the `MNIST_2NN` model, and a fixed 1% training sample. The user can choose 2–10 clients, 1–5 rounds, 1–3 local epochs, and a positive FedProx `mu`. Other training settings and filesystem paths are controlled by the backend.

> **Project status:** Authentication, experiment management, the worker, results/logs API, and the Angular flow are implemented. Direct CPU runner checks completed both algorithms; a browser walkthrough completed a two-round FedAvg run. A repeatable two-user, two-algorithm browser demonstration and handoff are still planned. This is a local university MVP, not a hosted service.

## What the app does

- An operator creates accounts; users log in with a one-hour JWT. Passwords are stored as Argon2id hashes.
- Users create and edit their own experiments. Editing stops after the first run is launched, and each run keeps a copy of its configuration.
- The API queues a run and returns promptly. A separate worker processes one queued job at a time in a fresh FLUKE subprocess.
- Angular polls active runs about every two seconds and shows status, recent logs, failure messages, per-round accuracy, and run history.
- The API checks ownership for experiments, runs, results, and logs. Another user's record returns `404`.

## Technology stack

| Part | Technologies |
|---|---|
| Frontend | Angular 22, TypeScript, RxJS, Angular Router, Reactive Forms, HTML, CSS |
| API and authentication | Python 3.11, FastAPI, Pydantic 2, Uvicorn, PyJWT, Argon2-cffi |
| Database | PostgreSQL 17, SQLAlchemy 2, psycopg 3, Alembic |
| Training | Pinned FLUKE revision, FedAvg, FedProx, MNIST, PyTorch through FLUKE; CPU subprocesses |
| Local tooling | Docker Compose, uv, npm, pytest, HTTPX, Ruff, Vitest |

```text
Angular browser ──HTTP──> FastAPI ──transactions──> PostgreSQL
                           │                            ▲
                           │ queues a run               │ claims/updates runs
                           └──────────────────────> local worker
                                                       │
                                                fresh FLUKE subprocess
                                                       │
                                                results and run logs
```

The API never trains inside an HTTP request. Only the runner subprocess imports FLUKE and PyTorch. Run artifacts live under `backend/artifacts/` by default and are ignored by Git.

## Prerequisites

- Python **3.11** and [uv](https://docs.astral.sh/uv/).
- Docker with the Compose v2 plugin, running locally, for PostgreSQL.
- Node.js and npm for the Angular app. `frontend/package.json` declares npm `11.20.0`.
- Network access for the first dependency, container, and MNIST downloads. The optional runner install includes the FLUKE/PyTorch stack.

The commands below assume a shell with `openssl`, run on the same machine, and use the checked-in lockfiles. On macOS, [the backend guide](backend/README.md#macos-with-colima) includes a Colima setup.

## Run locally

### 1. Clone and configure the backend

```sh
git clone https://github.com/eggspression/fluke-ui.git
cd fluke-ui/backend
uv python install 3.11
uv sync --locked --extra runner
cp .env.example .env
```

Generate two different local secrets with `openssl rand -hex 24` and `openssl rand -hex 32`. Edit the ignored `backend/.env` file so these entries contain your values:

```dotenv
POSTGRES_USER=fluke
POSTGRES_DB=fluke
POSTGRES_PASSWORD=<generated-database-password>
FLUKE_DATABASE_URL=postgresql://fluke:<same-database-password>@127.0.0.1:5432/fluke
FLUKE_JWT_SECRET=<generated-signing-secret>
FLUKE_DEVELOPMENT_ORIGINS=["http://localhost:4200"]
FLUKE_ARTIFACTS_DIR=artifacts
```

Use the same database password in both lines. A hexadecimal password avoids URL-encoding issues. Keep `.env` private; do not commit it. Leave `FLUKE_TEST_ADMIN_URL` empty for now.

### 2. Start PostgreSQL, migrate, and create a user

From `backend/`:

```sh
docker compose up -d --wait postgres
uv run --locked --extra runner alembic upgrade head
uv run --locked --extra runner fluke-admin create-user --email you@example.com
```

The account command prompts for a password without showing it. There is no browser registration page. The PostgreSQL container binds to `127.0.0.1:5432` and keeps its data in a named Docker volume.

### 3. Run the API, worker, and Angular app

Keep each command running in its own terminal:

```sh
# Terminal A, from backend/
uv run --locked --extra runner uvicorn fluke_backend.app:create_app --factory --host 127.0.0.1 --port 8000
```

```sh
# Terminal B, from backend/
uv run --locked --extra runner fluke-worker
```

```sh
# Terminal C, from frontend/
npm ci
npm start
```

Open <http://localhost:4200/> and sign in with the operator-created account. Create a FedAvg experiment with two clients, two rounds, and one local epoch, then launch it. The run page should move through `QUEUED` and `RUNNING` to `COMPLETED`, show recent log text, and display two accuracy rows. The first run can take longer because FLUKE may download MNIST. FedProx is also available in the form and requires a positive `mu`.

Useful local endpoints:

| URL | Purpose |
|---|---|
| <http://localhost:4200/> | Angular app |
| <http://127.0.0.1:8000/docs> | Interactive FastAPI API documentation |
| <http://127.0.0.1:8000/health/live> | API process liveness |
| <http://127.0.0.1:8000/health/ready> | Database and migration readiness |

The frontend currently calls `http://127.0.0.1:8000/api/v1`; use these addresses for the local demo. The JWT lives only in browser memory, so reloading or logging out requires another login.

## Run the checks

The backend tests that use PostgreSQL create and remove **disposable databases**. To enable them, set `FLUKE_TEST_ADMIN_URL` in `backend/.env` to the local maintenance database, using the same database password:

```dotenv
FLUKE_TEST_ADMIN_URL=postgresql://fluke:<same-database-password>@127.0.0.1:5432/postgres
```

Do not point this setting at the `fluke` application database. Without it, PostgreSQL tests report explicit skips. The real FLUKE success test also needs a prepared MNIST cache; after a successful local run, `backend/artifacts/mnist` can serve as `TEST_MNIST_DIR`.

```sh
# From backend/
TEST_MNIST_DIR="$(pwd)/artifacts/mnist" uv run --locked --extra runner pytest -q -rs
uv run --locked --extra runner ruff check .
uv run --locked --extra runner ruff format --check .
uv run --locked --extra runner alembic check
uv build
```

```sh
# From frontend/
npm test -- --watch=false
npm run build
```

On 2026-10-10, the full backend suite passed **84 tests without skips** with PostgreSQL and a prepared MNIST cache; the frontend passed **9 tests** and built. Check your own pytest summary for skips before treating a local run as equivalent. [Backend](backend/README.md) and [frontend](frontend/README.md) have more detailed commands.

## Common setup issues

| Symptom | Check |
|---|---|
| `/health/ready` returns `503` | Start PostgreSQL and apply `alembic upgrade head`; readiness checks the schema revision. |
| Browser reports a CORS error | Use `http://localhost:4200` and set that exact origin in `FLUKE_DEVELOPMENT_ORIGINS`, then restart the API. |
| Login fails | Create an account with `fluke-admin`; check its password and active status. |
| Worker stops on an unresolved `RUNNING` run | Inspect the named run and its process/log before manually correcting state. This MVP has no automatic crash recovery. |
| A new run does not start first | The worker processes the oldest queued record; inspect existing queued runs if reusing a development database. |
| PostgreSQL rejects a changed password | A new `.env` value does not change the password already stored in an existing Docker volume. |

Stop the API, worker, and Angular dev server with `Ctrl+C`. From `backend/`, run `docker compose down` to stop PostgreSQL while retaining its data volume. Run logs, result files, local `.env`, and downloaded datasets remain outside version control.

## Repository layout and scope

```text
backend/    FastAPI app, database migrations, account CLI, worker, FLUKE runner, tests
frontend/   Angular app, component tests, package lockfile
```

The MVP intentionally has one local worker and a small fixed training configuration. Automatic cancellation and recovery, GPU support, additional datasets, exports, model downloads, and production deployment are outside the current implementation.
