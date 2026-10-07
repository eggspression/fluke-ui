# FLUKE backend

Milestone A (BE-01–04) provides an installable API, PostgreSQL persistence,
reversible migrations, health endpoints, operator account management, and
one-hour JWT login. MVP-02 adds a separate FLUKE CPU runner. Experiment
resources and worker execution are later tickets.

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
Generate a separate signing secret with `openssl rand -hex 32` and put it in
`FLUKE_JWT_SECRET`. The API and account commands require both values.
Keep `.env` private; it is ignored. Blank or invalid database URLs stop API
startup with a validation error naming `database_url`; a missing or short signing
secret stops startup with an error naming `jwt_secret`. Environment variables
override `.env`; importing the application does not read settings or connect.
For a separate frontend dev server, set `FLUKE_DEVELOPMENT_ORIGINS` to a JSON
list of exact origins, such as `["http://localhost:4200"]`. Its default is empty.

```sh
docker compose up -d --wait postgres
uv run --locked alembic upgrade head
uv run --locked uvicorn fluke_backend.app:create_app --factory --reload
```

Visit <http://127.0.0.1:8000/health/live> for database-independent liveness,
<http://127.0.0.1:8000/health/ready> for database and migration readiness, and
<http://127.0.0.1:8000/docs> for generated API documentation. Readiness returns
503 when PostgreSQL is unavailable, the schema is absent, or its migration
revision differs. Import and startup do not connect to PostgreSQL or create tables;
only the explicit Alembic command changes the schema.

## Operator accounts

After migrating the database, run these commands from `backend/`:

```sh
uv run --locked fluke-admin create-user --email researcher@example.com
uv run --locked fluke-admin reset-password --email researcher@example.com
uv run --locked fluke-admin deactivate-user --email researcher@example.com
```

Create and reset prompt for the password with terminal echo disabled. The CLI
refuses to read a password if a secure terminal prompt is unavailable. There is
no password command-line argument; CLI output contains only the normalized email
and a status. Email addresses are validated and casefolded for uniqueness.
Passwords are stored as Argon2id hashes. Password reset changes future login credentials but does not invalidate an
already issued token. Deactivated accounts cannot log in or use an existing
token because authenticated requests reload the active user.

## API authentication

`POST /api/v1/auth/login` accepts JSON `email` and `password` and returns a
one-hour signed bearer token, its UTC expiry, and public user identity. Send
`Authorization: Bearer <token>` to `GET /api/v1/auth/me`. There is no server
logout route or refresh token; Angular will hold the token in memory and discard
it on logout. Invalid credentials, invalid or expired tokens, and inactive
accounts return a generic `401`. Password reset does not revoke an issued token;
it remains usable until expiry unless the account is deactivated. Tokens issued
before MVP-01, which contain a session ID, are rejected. HTTP and validation
errors use FastAPI's standard `detail` field.

## Try the API in Swagger UI

With PostgreSQL migrated and the API running, open
<http://127.0.0.1:8000/docs>. Create an account with `fluke-admin create-user`
first; there is no registration endpoint.

1. Expand **POST /api/v1/auth/login**, click **Try it out**, and enter the
   account email and password in the JSON body. Click **Execute**. A successful
   response is `200` and includes `access_token`, `expires_at`, and the user ID.
2. Copy only the `access_token` value. Click **Authorize** at the top of Swagger
   UI, paste the token without the `Bearer ` prefix, and confirm. Swagger adds
   the authorization header to protected requests.
3. Expand **GET /api/v1/auth/me** and click **Try it out → Execute**. Expect
   `200` with the same user ID and email. Use **Authorize → Logout** to clear
   Swagger's token from that browser tab.
4. Try **GET /health/live** and **GET /health/ready** without authorization;
   both return `200` when the API and migrated database are ready. A wrong
   password or invalid token returns `401`; a login body without `password`
   returns FastAPI's `422` validation response.

The token lasts one hour. Swagger's **Logout** clears its client-side token;
there is no `/api/v1/auth/logout` route. Keep real passwords and tokens out of
screenshots and shared logs.

## MVP-02: run FedAvg and FedProx directly

Install the optional training stack from `backend/`. The lockfile pins FLUKE
revision `37c54630f0b4d9d6164f003cbed0811019acc5e1`. The first install
downloads PyTorch and other training dependencies; the first run downloads
approximately 64 MB of MNIST files. Neither the API nor PostgreSQL is required
for these direct proofs.

```sh
uv sync --locked --extra runner
mkdir -p artifacts/mvp02
cat > artifacts/mvp02/fedavg.json <<'JSON'
{"algorithm":"fedavg","n_clients":2,"n_rounds":2,"local_epochs":1}
JSON
cat > artifacts/mvp02/fedprox.json <<'JSON'
{"algorithm":"fedprox","n_clients":2,"n_rounds":2,"local_epochs":1,"mu":0.3}
JSON
uv run --locked --extra runner python -m fluke_backend.runner_cli artifacts/mvp02/fedavg.json artifacts/mvp02/fedavg artifacts/mvp02/mnist
uv run --locked --extra runner python -m fluke_backend.runner_cli artifacts/mvp02/fedprox.json artifacts/mvp02/fedprox artifacts/mvp02/mnist
cat artifacts/mvp02/fedavg/result.json
cat artifacts/mvp02/fedprox/result.json
```

Each output directory contains `run.log` and, only after successful training,
`result.json` with two ordered round/accuracy entries. The CLI writes its
console output and any traceback to `run.log`; it exits nonzero on bad input,
initialization or training failure, interrupted or short runs, or a result
write failure. It removes a stale result before each attempt. The 1% sample
completed in about four seconds per algorithm on this Mac after dataset
download. Paths above are local, server-owned arguments; the JSON snapshot
cannot select datasets, code imports, or output paths. `artifacts/` is ignored
by Git.

Run the optional failure check with
`uv run --locked --extra runner pytest -q -m runner`; no real training succeeds in this test. The full base suite skips
this optional test when FLUKE is absent.

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

Unit tests use isolated settings and require neither PostgreSQL nor training
packages. PostgreSQL integration tests use a new database per test and drop it
afterward. To run them, set `FLUKE_TEST_ADMIN_URL` in ignored `.env` to a **local**
maintenance URL such as `postgresql://fluke:<password>@127.0.0.1:5432/postgres`.
Use the same password from `POSTGRES_PASSWORD`. The fixture rejects remote hosts
and URLs pointing at the application database. Do not add URL query parameters:
the fixture rejects them because PostgreSQL connection options can override the
host or database name. The fixture never migrates or deletes the
configured application database. Without this URL, PostgreSQL tests report
explicit skips. With the URL set, connection errors fail the suite. Use
`uv run --locked pytest -m postgres` to run only database tests and
`uv run --locked pytest -m 'not postgres'` for only unit tests.

Alembic migrations live in `backend/migrations/`. `uv run --locked alembic current`
shows the database revision. `uv run --locked alembic check` compares ORM metadata
with the applied schema. The first migration created `users` and `sessions`; MVP-01 adds a second
migration that drops `sessions` while preserving users. The current schema has
UUID user keys and timezone-aware timestamps. SQLAlchemy sessions commit when
their transaction block succeeds and roll back on errors. Revision compatibility
is checked on every readiness request.

No numeric coverage threshold is configured yet; Milestone A acceptance
behaviors are covered explicitly.

**BE-02 verification (2026-10-06):** All 27 tests pass with the local PostgreSQL
service, including upgrade/downgrade/reapply, rollback, and readiness tests.
`ruff check`, `ruff format --check`, `uv build`, `alembic current`, and
`alembic check` pass. The local development database is at revision
`20261006_0001`.

**MVP-01 verification (2026-10-07):** All 45 tests pass against local PostgreSQL,
including operator commands, one-hour tokens, migration preservation, reset and
deactivation behavior, invalid tokens, and CORS. Ruff and the Alembic schema
check pass. The upstream Starlette/HTTPX deprecation warning remains.

FastAPI generates the current OpenAPI schema at `/openapi.json` when the API runs.
No generated schema file is tracked.

For a clean install check, use a new temporary environment without altering `.venv`:

```sh
smoke_dir=$(mktemp -d)
UV_PROJECT_ENVIRONMENT="$smoke_dir/venv" uv sync --locked --no-editable
UV_PROJECT_ENVIRONMENT="$smoke_dir/venv" uv run --locked --no-editable pytest
```

## Dependency boundaries

Base dependencies are FastAPI, Pydantic, Pydantic Settings, Uvicorn, SQLAlchemy,
Alembic, psycopg, Argon2, email-validator, and PyJWT. The `dev`
group adds pytest, HTTPX, and Ruff. The optional `runner` extra installs the
pinned FLUKE stack for direct CPU runs. The ordinary API install and API imports
do not need FLUKE or PyTorch.

The MVP will add experiment, run, and worker code only when those
responsibilities are implemented; the active scope is in
[TICKETS.md](../docs/TICKETS.md).

If uv's normal cache is unavailable in a restricted workspace, set
`UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` to writable, ignored local directories.
See the [uv project guide](https://docs.astral.sh/uv/guides/projects/) and
[Pydantic Settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).
