# Backend code walkthrough — completed tickets

This document explains **implemented code only**. As checked on **2026-10-08**, BE-01–04 and MVP-01–03 are complete. The [roadmap](TICKETS.md) remains the source for pending tickets and completion criteria; [BACKEND.md](BACKEND.md) describes the target architecture, [backend/README.md](../backend/README.md) contains runnable setup commands, and [CONTEXT.MD](../CONTEXT.MD) is the next-session handoff. Recheck source and tests if you read this after the snapshot date.

## Start with the part that runs now

The current backend can answer a health request, connect to a migrated PostgreSQL database, let an operator create an account, and let that user log in and inspect their identity. Client logout discards the token; there is no server logout route. A separate CLI runner can execute FedAvg or FedProx in its own process. Owned experiments and `QUEUED` run records are available through the API. There is no worker or Angular source yet.

```text
Operator CLI ── create/reset/deactivate ─┐
                                        ▼
HTTP client ── login/me ── FastAPI ── PostgreSQL users

JSON snapshot ── separate runner process ── FLUKE ── result.json + run.log
```

There are four useful layers to recognize. **Settings** reads and validates configuration. The **API** handles HTTP requests and responses. A **service** such as `AccountService` or `TokenService` contains the behavior. **Models** map Python objects to PostgreSQL rows. A **transaction** is the database boundary: its changes commit together, or roll back together if an error occurs. A **migration** changes the database schema; defining a SQLAlchemy model alone does not create its table.

To follow the existing code, start in `backend/` and read the linked files in each ticket section in order. The examples use fictional accounts. Never put a real password, JWT, or database URL in a committed file or shell history.

## Milestone A — Foundation and authentication (implemented)

Milestone A is the runnable foundation. Each subsection below follows one behavior through the actual source, explains why the boundary exists, and points to a test that proves it. The current code reflects later tickets too: for example, `Settings` now requires a JWT secret because BE-04 added one after BE-01.

### BE-01 — Reproducible backend setup

**What exists:** [pyproject.toml](../backend/pyproject.toml) declares Python 3.11, the `fluke-backend` package, base dependencies, and the `fluke-admin` entry point. [uv.lock](../backend/uv.lock) fixes the resolved dependency set so a fresh install does not silently choose newer versions. The optional `runner` extra added in MVP-02 installs FLUKE and PyTorch; a base API install still omits them. [compose.yaml](../backend/compose.yaml) starts PostgreSQL 17, binds its port to `127.0.0.1`, and keeps data in a named volume. [`.env.example`](../backend/.env.example) lists variable names but contains no working credentials; the real `.env` is ignored by Git.

**Trace a request, step by step:**

1. `uvicorn fluke_backend.app:create_app --factory` imports [app.py](../backend/src/fluke_backend/app.py) and calls `create_app()`. Importing the module itself does not start PostgreSQL or load training libraries.
2. `create_app()` constructs [Settings](../backend/src/fluke_backend/settings.py). `BaseSettings` reads `FLUKE_` environment variables and the local `.env`; explicit environment variables take priority. `database_url` and `jwt_secret` are `SecretStr` values, so ordinary object representations hide them. Validators reject a non-PostgreSQL URL, a signing secret shorter than 32 characters, and malformed or wildcard development origins.
3. `create_app()` creates a `Database` object and registers routes. Creating the SQLAlchemy engine is lazy: it does not open a connection or create tables. The app's lifespan closes the engine pool when the app shuts down.
4. `GET /health/live` returns `{"status":"ok"}` without querying the database. It means the HTTP process is alive. It does **not** prove migrations or PostgreSQL are ready; BE-02 adds that distinction.

**Why these choices matter:** A machine may have a healthy API process while its database is down. A liveness endpoint that required PostgreSQL would blur those two failures. Keeping FLUKE out of the API install also keeps startup and simple tests lightweight.

**Follow it yourself:** Read `create_app()` and `liveness()` in [app.py](../backend/src/fluke_backend/app.py), then `Settings` in [settings.py](../backend/src/fluke_backend/settings.py). Run `uv run --locked pytest -q tests/test_app.py tests/test_settings.py` from `backend/`. The `test_import_and_liveness_do_not_connect_or_load_training_libraries` test deliberately rejects database connections and FLUKE/PyTorch imports; it proves the boundary rather than merely checking an HTTP status. For real startup commands, use [backend/README.md](../backend/README.md).

### BE-02 — Database lifecycle and migrations

**What exists:** [database.py](../backend/src/fluke_backend/database.py) creates a psycopg-backed SQLAlchemy engine and a transaction factory. [models.py](../backend/src/fluke_backend/auth/models.py) defines the `User` object-relational mapping (ORM) model: a Python object mapped to a database row. The first [Alembic migration](../backend/migrations/versions/20261006_0001_users_sessions.py) created `users` and `sessions`; the [MVP-01 migration](../backend/migrations/versions/20261007_0002_drop_sessions.py) removes `sessions` while retaining users. The current schema has `users`, `experiments`, `runs`, and `alembic_version`, with UUID keys and timezone-aware timestamps. The [MVP-03 migration](../backend/migrations/versions/20261008_0003_experiments_runs.py) adds the latter two resource tables. Alembic is the schema migration tool; defining an ORM model alone does not change PostgreSQL.

**Trace a database write, step by step:**

1. A service calls `with database.transaction() as session:`. `Database.transaction()` returns `sessionmaker.begin()`, which opens a session and transaction for that block.
2. The service adds or changes ORM objects. `session.flush()` sends pending SQL early so, for example, a new UUID is available before leaving the block. A flush is **not** a commit: an exception afterward still rolls back the write.
3. When the block exits normally, SQLAlchemy commits and closes the session. If the block raises, it rolls back and closes. `expire_on_commit=False` lets the service read the returned object's fields after commit.
4. At shutdown, `Database.close()` disposes the engine's connection pool. It does not delete tables or data.

**Trace readiness:** `GET /health/ready` in [app.py](../backend/src/fluke_backend/app.py) calls `Database.schema_is_current()`. That function opens a real connection and reads `alembic_version`; it compares the value with `EXPECTED_REVISION`. A missing database, missing migration table, or wrong revision leads to `503`. `/health/live` still answers `200`, which tells an operator the process is up but its dependency is not ready.

**Why migrations and tests are separate:** `migrations/env.py` registers model metadata for Alembic and takes a fixture-supplied database URL during tests. [conftest.py](../backend/tests/conftest.py) creates a randomly named **disposable local PostgreSQL database** for each integration test and drops it afterward. It rejects an unsafe test-admin target. This is important because a migration downgrade intentionally removes tables; it must never run against the ordinary application database during a test.

**Follow it yourself:** Read [test_database.py](../backend/tests/test_database.py) in order: migrate to current schema, preserve an existing user while removing sessions, downgrade/reapply, commit timestamps, rollback after flush, and readiness before/after migration. Run `uv run --locked pytest -q tests/test_database.py` with the documented local `FLUKE_TEST_ADMIN_URL`. If the test is skipped, you have **not** verified the PostgreSQL behavior. `uv run --locked alembic current` shows the local app database's revision; `uv run --locked alembic check` compares current ORM metadata to it.

### BE-03 — Operator-managed accounts

**What exists:** The installed `fluke-admin` command comes from [cli.py](../backend/src/fluke_backend/auth/cli.py). It offers `create-user`, `reset-password`, and `deactivate-user`; there is no public registration endpoint. [accounts.py](../backend/src/fluke_backend/auth/accounts.py) implements the account changes. [passwords.py](../backend/src/fluke_backend/auth/passwords.py) wraps Argon2 hashing and verification. These commands use only the `users` table.

**Trace `create-user`, step by step:**

1. The CLI accepts `--email`, but no password argument. Its parser turns invalid or unknown arguments into a generic message instead of echoing a mistaken secret from a command line.
2. `getpass.getpass()` reads the password with terminal echo disabled. If the terminal cannot guarantee that, `GetPassWarning` becomes an error and the command stops before reading visible input. `deactivate-user` needs no password prompt.
3. `AccountService.create_user()` calls `normalize_email()`. That helper trims whitespace, validates email syntax with deliverability checks disabled, then casefolds for a canonical value. It does **not** prove that the mailbox receives mail. For example, `  Alice@Example.COM  ` is stored as `alice@example.com`.
4. `_new_password_hash()` calls Argon2. The database row stores only `password_hash`, never the original password. The service inserts it inside a transaction and flushes. If PostgreSQL reports the named `uq_users_email` constraint, it raises the safe `AccountExistsError`; the database constraint remains the final guard against concurrent duplicates.
5. The CLI prints the normalized email and action status. It does not print the password or hash.

**Trace reset and deactivation:** Both methods select the user with `with_for_update()`, which locks that database row until their transaction ends. Reset replaces the hash; deactivation sets `is_active=False`. Reset does not invalidate an existing JWT, which remains valid until its one-hour expiry. Deactivation immediately blocks that JWT at the next request because authentication reloads the user and checks `is_active`.

**Follow it yourself:** Read `normalize_email()`, `create_user()`, `reset_password()`, and `deactivate_user()` in [accounts.py](../backend/src/fluke_backend/auth/accounts.py). Compare them with [test_accounts.py](../backend/tests/test_accounts.py): the tests check the `$argon2id$` prefix, plaintext absence, case-variant duplicate rejection, changed hash, and inactive state. [test_account_cli.py](../backend/tests/test_account_cli.py) checks secret-free output and refusal of unsafe prompts. Run `uv run --locked pytest -q tests/test_accounts.py tests/test_account_cli.py` with disposable PostgreSQL enabled. An operator can try `uv run --locked fluke-admin create-user --email alice@example.com` against their configured local database; the password prompt is interactive.

### BE-04 and MVP-01 — One-hour JWT authentication

**What exists:** [auth/api.py](../backend/src/fluke_backend/auth/api.py) defines `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, and the reusable `get_current_user` dependency. [auth/tokens.py](../backend/src/fluke_backend/auth/tokens.py) issues and verifies a signed JSON Web Token (JWT). The token contains an issuer (`iss`), user ID (`sub`), issue time (`iat`), and one-hour expiry (`exp`). A signature detects tampering; claims are not encrypted. There is no login-session database row or server logout route. The signing key comes from `FLUKE_JWT_SECRET` in ignored local configuration.

**Trace login, step by step:**

1. A client sends JSON with `email` and `password` to `/api/v1/auth/login`. `LoginRequest.password` is Pydantic `SecretStr`, which hides it in ordinary model representations. Transport still needs HTTPS outside local development.
2. `TokenService.login()` normalizes the email, reads the user, checks `is_active`, and verifies the Argon2 hash. Unknown email, wrong password, and inactive user all produce the same `401` response.
3. After the read transaction, the service signs a JWT with HS256. The API returns its string, UTC expiry, and the public user ID/email. No password hash appears in the response.

A successful response has this shape (values are placeholders):

```json
{
  "access_token": "<signed JWT>",
  "token_type": "bearer",
  "expires_at": "<UTC timestamp>",
  "user": {"id": "<user UUID>", "email": "alice@example.com"}
}
```

**Trace `/me`:** `get_current_user()` reads `Authorization: Bearer <token>`. `TokenService.authenticate()` pins HS256 and the issuer, requires and verifies the claims and expiry, parses the user UUID, and loads that user from PostgreSQL. It rejects missing, malformed, forged, expired, or older session-based tokens and inactive or deleted users. It does not consult a token table. A password reset leaves an already issued token valid until its signed expiry; account deactivation makes it fail at the next authenticated request. Angular's eventual logout action will simply discard its in-memory token.

**Trace errors and browser access:** [app.py](../backend/src/fluke_backend/app.py) uses FastAPI's ordinary `detail` responses for HTTP and validation errors. `FLUKE_DEVELOPMENT_ORIGINS` configures exact allowed browser origins; the default list is empty. Cross-origin resource sharing (CORS) decides which browser origins may read responses. It does not authorize data access. MVP-03 experiment and run endpoints filter every resource lookup by the authenticated owner.

**Follow it yourself:** Read `login()` and `get_current_user()` in [auth/api.py](../backend/src/fluke_backend/auth/api.py), then `TokenService.login()` and `authenticate()` in [auth/tokens.py](../backend/src/fluke_backend/auth/tokens.py). [test_auth_api.py](../backend/tests/test_auth_api.py) covers one-hour claims, `/me`, operator-created users, invalid tokens, reset, deactivation, FastAPI errors, and CORS. Run `uv run --locked pytest -q tests/test_auth_api.py` with disposable PostgreSQL enabled. The live API generates its schema at `/openapi.json`; no schema snapshot is tracked.

## Milestone A — complete test guide

This walkthrough tests **BE-01–04 as they work after MVP-01**. It covers setup, migrations, health, account commands, login, JWT authentication, reset, deactivation, browser access, and the automated checks. Use a throwaway account: deactivation has no reactivation command. The commands below run from `backend/` unless stated otherwise. Keep real passwords and tokens out of shell arguments, screenshots, Git, and shared logs.

### 1. Prepare the local environment

```sh
cd /Users/eggspression/Documents/code/projects/fluke-ui/backend
uv python install 3.11
uv sync --locked
test -f .env || cp .env.example .env
chmod 600 .env
```

On a new setup, generate separate values with `openssl rand -hex 24` and `openssl rand -hex 32`, then edit the ignored `.env`. Set `POSTGRES_PASSWORD` to the first value, `FLUKE_DATABASE_URL` to `postgresql://fluke:<password>@127.0.0.1:5432/fluke`, and `FLUKE_JWT_SECRET` to the second value. For the complete integration suite, also set `FLUKE_TEST_ADMIN_URL` to `postgresql://fluke:<password>@127.0.0.1:5432/postgres`. Replace `<password>` with the same PostgreSQL password, not the JWT secret. The test-admin URL must target the local `postgres` maintenance database, never `fluke`; the fixture creates and drops its own random databases. See [backend/README.md](../backend/README.md) for setup details. Do not overwrite an existing `.env` just to follow this walkthrough.

On this macOS development setup, start Colima if it is stopped. Then start PostgreSQL and apply the current migration:

```sh
colima start
docker compose up -d --wait postgres
uv run --locked alembic upgrade head
uv run --locked alembic current
uv run --locked alembic check
```

If Colima is already running, skip `colima start`. Expect `20261008_0003 (head)` from `alembic current` and `No new upgrade operations detected` from `alembic check`. The current schema has `users`, `experiments`, `runs`, and `alembic_version`, not `sessions`. The automated migration test below proves that upgrading from the earlier revision preserves existing users and that downgrade/reapply works. Do **not** downgrade your application database to test that behavior.

### 2. Start the API and test health

In terminal A, leave the API running:

```sh
uv run --locked uvicorn fluke_backend.app:create_app --factory --host 127.0.0.1 --port 8000
```

In terminal B, from `backend/`:

```sh
curl -i http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/health/ready
curl -I http://127.0.0.1:8000/docs
curl -I http://127.0.0.1:8000/openapi.json
```

Expect `200` for all four. Both health responses have `{"status":"ok"}`. `/health/live` only proves the HTTP process is alive; `/health/ready` checks PostgreSQL and migration revision. A missing database or stale schema makes readiness return `503` while liveness stays `200`. The automated tests exercise that failure without disrupting the application database.

### 3. Create a throwaway operator-managed account

In terminal B, choose a unique email and run the interactive command:

```sh
TEST_EMAIL="milestone-a-$(date +%s)@example.com"
echo "$TEST_EMAIL"
uv run --locked fluke-admin create-user --email "$TEST_EMAIL"
```

Enter a password at the hidden prompt; remember it for the Swagger steps. Expect `Created <normalized email>`. No public sign-up route exists. The command accepts no `--password` argument. Automated account tests also verify email normalization, case-insensitive duplicates, Argon2id hashes, missing users, and refusal of an insecure password prompt.

### 4. Test login and protected requests in Swagger UI

Open <http://127.0.0.1:8000/docs>. Use the printed `TEST_EMAIL` and the password from step 3.

1. Expand **POST /api/v1/auth/login**, click **Try it out**, enter `email` and `password` in the JSON body, then click **Execute**. Expect `200`, `token_type: "bearer"`, a user ID/email, `expires_at` about one hour ahead, and an `access_token`. Do not share the token.
2. Expand **GET /api/v1/auth/me** before authorizing and execute it. Expect `401` with FastAPI's `detail` field.
3. Click **Authorize** at the top of Swagger. Paste only the `access_token` value, without `Bearer `. Swagger supplies the prefix. Execute **GET /api/v1/auth/me** again. Expect `200` with the same ID and email from login.
4. Use **Authorize → Logout** to clear Swagger's token, then execute `/auth/me` again. Expect `401`. This only clears Swagger's copy of the token; it does not revoke the signed token on the server.

Try these error cases in Swagger before resetting the account:

| Request | Expected result |
|---|---|
| Login with the correct email and a wrong password | `401`, generic credential error |
| Login with an unknown email | `401`, same generic credential error |
| Login JSON without `password` | `422`, FastAPI validation `detail` |
| `/auth/me` with no token or a fabricated token | `401` |
| `/api/v1/auth/logout` | Not listed in Swagger; a direct request returns `404` |

Expired, forged, malformed-subject, unknown-user, and older session-based JWTs are checked by [test_auth_api.py](../backend/tests/test_auth_api.py). They are easier and safer to verify with isolated tests than by creating real expired credentials manually.

### 5. Test reset and deactivation

Log in again in Swagger and leave its token authorized. In terminal B, reset the **throwaway** account:

```sh
uv run --locked fluke-admin reset-password --email "$TEST_EMAIL"
```

Enter a new password at the hidden prompt. Back in Swagger, `/auth/me` with the **old token** should still return `200`: reset changes future login credentials but does not revoke issued one-hour JWTs. Login with the old password should return `401`; login with the new password should return `200`. Keep or authorize the new token for the next check.

Finally deactivate that test account in terminal B:

```sh
uv run --locked fluke-admin deactivate-user --email "$TEST_EMAIL"
```

Expect `Deactivated <email>`. `/auth/me` with either old or new token now returns `401`, and login with the new password also returns `401`. Authentication reloads the user on every protected request and rejects inactive accounts. Do not use a real account for this step; no reactivation command exists.

### 6. Run the automated checks

From `backend/`, with `FLUKE_TEST_ADMIN_URL` configured as in step 1:

```sh
uv run --locked pytest -q -rs
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked alembic check
uv build
```

The full runner-enabled backend suite on 2026-10-08 passed **74 tests** with PostgreSQL and no skips. A fresh base installation skips the optional FLUKE test. Inspect your own pytest summary: if integration tests are **skipped**, you have not verified database behavior. The upstream Starlette/HTTPX deprecation warning does not fail the suite. `ruff check` and `ruff format --check` should pass; Alembic should report no pending schema operations; `uv build` should produce a wheel and source distribution.

| Test file | What it proves |
|---|---|
| [test_settings.py](../backend/tests/test_settings.py), [test_app.py](../backend/tests/test_app.py) | Required settings, credential-safe errors, liveness/readiness split, and no database connection or FLUKE/PyTorch import during import/liveness. |
| [test_database.py](../backend/tests/test_database.py), [test_postgres_guard.py](../backend/tests/test_postgres_guard.py) | Current and reversible migrations, existing-user preservation, UTC/UUID records, transaction rollback, readiness, and safe disposable-database targeting. |
| [test_accounts.py](../backend/tests/test_accounts.py), [test_account_cli.py](../backend/tests/test_account_cli.py) | Argon2id storage, email uniqueness, reset/deactivation, secret-free CLI output, and secure prompts. |
| [test_auth_api.py](../backend/tests/test_auth_api.py) | Operator-created user login, one-hour JWT, `/me`, generic failures, invalid tokens, reset/deactivation behavior, FastAPI errors, and CORS. |

To focus on one area, run `uv run --locked pytest -q tests/test_auth_api.py` or `uv run --locked pytest -q tests/test_database.py`. The database tests create and remove separate test databases; they do not downgrade or erase the configured application database.

### 7. Optional CORS check and shutdown

For a browser served separately at `http://localhost:4200`, set `FLUKE_DEVELOPMENT_ORIGINS=["http://localhost:4200"]` in `.env` and restart the API. Then run:

```sh
curl -i -X OPTIONS http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Origin: http://localhost:4200' \
  -H 'Access-Control-Request-Method: POST'
curl -i -X OPTIONS http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Origin: http://unlisted.example' \
  -H 'Access-Control-Request-Method: POST'
```

The first response should include `Access-Control-Allow-Origin: http://localhost:4200`. The second should return `400` without an allow-origin header. [test_auth_api.py](../backend/tests/test_auth_api.py) checks both cases. CORS controls browser access to responses; it does not replace JWT authentication.

Stop Uvicorn with `Ctrl+C`. `docker compose down` stops PostgreSQL but retains its named volume. Avoid `docker compose down -v` if you want to keep local users. Milestone A ends here; the separate MVP-02 runner is explained next.

## MVP-02 — Two real FLUKE CPU proofs (implemented)

**What exists:** [runner.py](../backend/src/fluke_backend/runner.py) validates the small JSON snapshot, maps it to fixed MNIST/IID/CPU settings, collects global accuracy, and writes a complete result file. [runner_cli.py](../backend/src/fluke_backend/runner_cli.py) is the subprocess entry point. The optional `runner` dependency group pins FLUKE to revision `37c54630f0b4d9d6164f003cbed0811019acc5e1`; a normal API install still omits FLUKE and PyTorch. The runner CLI itself has no HTTP routes or database writes; MVP-03 stores only queued run records.

**Trace one run, step by step:**

1. A trusted caller runs `python -m fluke_backend.runner_cli <config.json> <output-dir> <dataset-dir>` in a fresh process. The JSON contains only `algorithm`, `n_clients`, `n_rounds`, `local_epochs`, and optional FedProx `mu`. `RunConfig` rejects unknown fields, out-of-range values, noninteger counts, nonfinite `mu`, and any supplied `mu` for FedAvg. Paths are command arguments chosen by the caller, never JSON fields from a user.
2. The CLI creates the output directory, removes a result file left by an earlier attempt, and redirects stdout/stderr to `run.log`. Only after validating JSON does it import FLUKE and PyTorch. It maps the snapshot to `MNIST_2NN`, IID, CPU, seed 42, all clients participating, one evaluation per round, and `sampling_perc: 0.01`. The dataset cache is a caller-supplied directory; FLUKE downloads the full MNIST files on the first run, then samples training and evaluation through its data splitter.
3. `execute()` follows FLUKE's public construction path: `Configuration.from_dict`, `FlukeENV.configure`, `Datasets.get`, `DataSplitter`, `ClassificationEval`, `FedAVG` or `FedProx`, `set_callbacks`, and `algorithm.run`. It does not call the private CLI function `_run_federation()`. A new process matters because `FlukeENV` is process-global state.
4. `RoundResults` receives `server_evaluation`, `end_round`, `interrupted`, `early_stop`, and `finished` observer events. It keeps global accuracy only for rounds that ended, ignores FLUKE's repeated final evaluation, and requires exactly the requested rounds with finite accuracy from 0 to 1. FLUKE can report `finished` after an interruption, so that event alone is insufficient.
5. Only after validation does `write_result()` publish `result.json` by renaming a temporary file. Exceptions return a nonzero exit and a traceback in `run.log`. The future worker must also check process exit and parse the result before it marks a run complete.

Successful `result.json` has this shape:

```json
{"algorithm":"fedavg","rounds":[{"round":1,"accuracy":0.17188},{"round":2,"accuracy":0.125}]}
```

Those numbers are one observed proof, not target accuracy. With two clients, two rounds, one local epoch, and the 1% sample on this Mac, cached-dataset reruns took 3.98 seconds for FedAvg and 4.16 seconds for FedProx. The first run additionally downloaded approximately 64 MB of MNIST data and initialized the training stack; first-run time depends on network and cache state.

### MVP-02 — complete test guide

These checks run the runner directly. The API, PostgreSQL, and an account are not needed for steps 1–5. Use the same terminal for the commands so the `guide_dir` variable remains set. Output goes under ignored `backend/artifacts/`; no dataset, log, or result file belongs in Git.

#### 1. Install the optional training stack and prepare fresh inputs

From the repository root:

```sh
cd backend
uv sync --locked --extra runner
mkdir -p artifacts
guide_dir=$(mktemp -d artifacts/mvp02-guide.XXXXXX)
printf 'Proof directory: %s\n' "$guide_dir"

cat > "$guide_dir/fedavg.json" <<'JSON'
{"algorithm":"fedavg","n_clients":2,"n_rounds":2,"local_epochs":1}
JSON
cat > "$guide_dir/fedprox.json" <<'JSON'
{"algorithm":"fedprox","n_clients":2,"n_rounds":2,"local_epochs":1,"mu":0.3}
JSON
```

`uv sync --locked --extra runner` installs the FLUKE revision in the lockfile and its PyTorch dependencies. The two JSON files contain exactly the values the future worker will pass. The three path arguments in the next step are chosen outside the JSON. The first run may download the full MNIST dataset into `$guide_dir/mnist`, so it needs network access and takes longer than a cached run. The runner uses 1% of that dataset for training and evaluation.

#### 2. Run both algorithms in separate processes

```sh
uv run --locked --extra runner python -m fluke_backend.runner_cli \
  "$guide_dir/fedavg.json" "$guide_dir/fedavg" "$guide_dir/mnist"
printf 'FedAvg exit: %s\n' "$?"

uv run --locked --extra runner python -m fluke_backend.runner_cli \
  "$guide_dir/fedprox.json" "$guide_dir/fedprox" "$guide_dir/mnist"
printf 'FedProx exit: %s\n' "$?"
```

Expect exit `0` for each. The commands print little to the terminal because the runner puts FLUKE's output in each run's `run.log`. Each output directory should also contain `result.json`. The two calls start fresh Python processes; sharing only the MNIST cache is intentional. A cached run took about four seconds per algorithm on the machine used for the 2026-10-07 proof; this is an observation, not a timeout or accuracy target.

#### 3. Check the result and readable log

```sh
rg -n 'Round: 1|Round: 2|Training completed' \
  "$guide_dir/fedavg/run.log" "$guide_dir/fedprox/run.log"

uv run --locked --extra runner python - "$guide_dir" <<'PY'
import json
import math
import sys
from pathlib import Path

root = Path(sys.argv[1])
for algorithm in ("fedavg", "fedprox"):
    result = json.loads((root / algorithm / "result.json").read_text())
    assert result["algorithm"] == algorithm
    assert [item["round"] for item in result["rounds"]] == [1, 2]
    assert all(
        isinstance(item["accuracy"], (int, float))
        and math.isfinite(item["accuracy"])
        and 0 <= item["accuracy"] <= 1
        for item in result["rounds"]
    )
    print(algorithm, result["rounds"])
PY
```

Expect two round headings and the completion line in each log, then one printed list of two valid accuracy records per algorithm. The JSON parser and assertions catch a missing file, malformed JSON, missing round, wrong algorithm, or invalid accuracy. Do not compare accuracy with the example values above: training-library or hardware differences can change the numbers.

#### 4. Prove invalid input fails and clears a stale result

```sh
printf '%s\n' '{"algorithm":"unknown"}' > "$guide_dir/invalid.json"
mkdir -p "$guide_dir/invalid"
printf '%s\n' '{"stale":true}' > "$guide_dir/invalid/result.json"

if uv run --locked --extra runner python -m fluke_backend.runner_cli \
  "$guide_dir/invalid.json" "$guide_dir/invalid" "$guide_dir/mnist"; then
  printf 'FAIL: invalid configuration was accepted\n'
else
  printf 'Expected nonzero exit: %s\n' "$?"
fi
rg -n 'Runner failed|algorithm' "$guide_dir/invalid/run.log"
test ! -e "$guide_dir/invalid/result.json"
```

Expect a nonzero exit, a validation diagnostic naming `algorithm`, and no `result.json` despite the file placed there before the attempt. `test ! -e` prints nothing when that last condition holds. [test_runner.py](../backend/tests/test_runner.py) also checks invalid client/round/epoch counts, FedAvg `mu`, nonpositive or nonfinite FedProx `mu`, and extra dataset or path fields. Those values must be rejected before FLUKE is imported.

#### 5. Prove an execution failure leaves a diagnostic log, not a result

Give FLUKE a regular file where it expects a dataset directory. This causes a real initialization failure without altering the successful run directories:

```sh
printf '%s\n' 'not a directory' > "$guide_dir/not-a-directory"
if uv run --locked --extra runner python -m fluke_backend.runner_cli \
  "$guide_dir/fedavg.json" "$guide_dir/failure" "$guide_dir/not-a-directory"; then
  printf 'FAIL: execution failure was accepted\n'
else
  printf 'Expected nonzero exit: %s\n' "$?"
fi
rg -n 'Runner failed|NotADirectoryError' "$guide_dir/failure/run.log"
test ! -e "$guide_dir/failure/result.json"
```

Expect a nonzero exit, `NotADirectoryError` in the traceback, and no result file. A zero exit by itself never proves success: `RoundResults` also requires every requested round, a `finished` event without interruption, and a finite global accuracy for each round. The focused unit tests simulate short, interrupted, duplicate-final-evaluation, and invalid-accuracy event sequences without retraining MNIST.

#### 6. Run the automated checks

For the runner ticket alone, with the optional extra installed:

```sh
uv run --locked --extra runner pytest -q -rs tests/test_runner.py
uv run --locked --extra runner ruff check .
uv run --locked --extra runner ruff format --check .
uv build
```

The focused suite checks the input mapping and result rules, runs a bad JSON subprocess, and triggers one real FLUKE initialization failure. It passed **23 tests** on 2026-10-07; confirm your pytest summary has no skipped runner test. The latter three commands check Python lint, formatting, and the package build; they do not run training.

To check the entire backend, first use the Milestone A setup above to start local PostgreSQL and configure `FLUKE_TEST_ADMIN_URL` in ignored `.env`. Then run:

```sh
uv run --locked --extra runner pytest -q -rs
uv run --locked --extra runner alembic check
```

The 2026-10-07 full check passed **68 tests** with PostgreSQL and the runner extra available. Read the pytest summary: a skipped PostgreSQL test means the database behavior was not verified, and a skipped runner test means the extra was not available. MVP-02 changes no database schema, so Alembic should report `No new upgrade operations detected`. A normal `uv sync --locked` later returns the environment to the lightweight API install. Keep `$guide_dir` until you have inspected its logs; the directory remains ignored by Git.

## MVP-03 — Owned experiments and queued run requests (implemented)

**What exists:** [ExperimentForm](../backend/src/fluke_backend/experiments/api.py) adds a trimmed, nonempty name of at most 120 characters to the proven [RunConfig](../backend/src/fluke_backend/runner.py). The request accepts only `algorithm`, `n_clients`, `n_rounds`, `local_epochs`, and FedProx `mu` alongside the name. Counts are strict integers; `mu` must be a positive JSON number, so booleans and numeric strings are rejected. FedAvg rejects `mu` entirely. Defaults are four clients, two rounds, one local epoch, and FedProx `mu: 0.3`. Dataset, model, distribution, device, seed, sample fraction, import names, and paths are server controlled.

[models.py](../backend/src/fluke_backend/experiments/models.py) maps `experiments` and `runs` to PostgreSQL; the [migration](../backend/migrations/versions/20261008_0003_experiments_runs.py) creates both tables. Each row has an owner UUID. An experiment keeps its name, configuration JSON, and creation/update times. A run keeps its experiment and owner IDs, a separate configuration JSON value, status, timestamps, and a nullable short failure message. MVP-03 creates only `QUEUED` runs. `started_at`, `finished_at`, and `failure_message` remain null until the worker arrives in MVP-04.

**Trace an HTTP request:** [app.py](../backend/src/fluke_backend/app.py) registers the [experiment router](../backend/src/fluke_backend/experiments/api.py). The existing `get_current_user` dependency verifies the one-hour JWT and active user on every route. The router parses the form and returns ordinary FastAPI `422` validation responses. [ExperimentService](../backend/src/fluke_backend/experiments/service.py) scopes all reads and writes to that user's ID; another user's UUID and a missing UUID both produce `404`. Create returns `201`, launch returns `202`, and a full replacement `PATCH` returns `409` after any run exists. There is no separate validation endpoint.

Edit and launch both lock the experiment row while their transaction runs. Launch copies the current configuration into a new run, commits `QUEUED`, and returns immediately. It does not import FLUKE, start a process, or write logs. The run snapshot remains the same even if the experiment row changes independently. Per-experiment history and the owned run detail are available now; training, accuracy, and log routes are MVP-04.

### MVP-03 — complete test guide

Use two throwaway users and the local PostgreSQL service. Commands below run from `backend/`. The API requests use Swagger UI so tokens and passwords do not enter shell history. The account and experiment rows persist in the local development volume; choose test accounts you can leave there.

#### 1. Prepare the schema and two users

Follow Milestone A step 1 to configure ignored `.env` and `FLUKE_TEST_ADMIN_URL`. Start Colima if needed, then run:

```sh
colima start
docker compose up -d --wait postgres
uv run --locked alembic upgrade head
uv run --locked alembic current
uv run --locked alembic check
uv run --locked fluke-admin create-user --email mvp03-alice@example.com
uv run --locked fluke-admin create-user --email mvp03-bob@example.com
```

Skip `colima start` if it is already running. Each account command prompts for a password without echo. Use unique addresses if those accounts already exist. Expect `20261008_0003 (head)` and `No new upgrade operations detected` from Alembic. The migration is additive to the existing users table; do not downgrade your application database for a test.

Start the API in a second terminal:

```sh
uv run --locked uvicorn fluke_backend.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/docs>. `GET /health/ready` should return `200` with `{"status":"ok"}`. A stale schema returns `503` until `alembic upgrade head` runs.

#### 2. Create, read, and edit Alice's experiment

In Swagger, log in with **POST /api/v1/auth/login** using Alice's address and password. Copy the `access_token` into **Authorize** without a `Bearer ` prefix. Try **POST /api/v1/experiments** with:

```json
{"name":"First proof","algorithm":"fedavg"}
```

Expect `201` and record the returned experiment `id`. Its `config` should contain `fedavg`, `n_clients: 4`, `n_rounds: 2`, and `local_epochs: 1`, with no `mu`. Both timestamps should be present. **GET /api/v1/experiments** returns an array containing it; **GET /api/v1/experiments/{experiment_id}** returns the same record.

Use **PATCH /api/v1/experiments/{experiment_id}** with that ID and a complete replacement form:

```json
{"name":"Prox proof","algorithm":"fedprox","n_clients":2,"n_rounds":2,"local_epochs":1,"mu":0.5}
```

Expect `200` with the new name and full FedProx configuration. A PATCH body needs `name` and `algorithm`; omitted numeric fields take their defaults. It does not merge into the old configuration.

#### 3. Queue a run and inspect its snapshot

Use **POST /api/v1/experiments/{experiment_id}/runs** with the same ID and no body. Expect `202`, `status: "QUEUED"`, a new run `id`, and a `config` equal to the edited experiment's configuration. `failure_message`, `started_at`, and `finished_at` should be null. **GET /api/v1/runs/{run_id}** returns that run; **GET /api/v1/experiments/{experiment_id}/runs** returns it in a newest-first array.

Retry the PATCH from step 2. It should now return `409` with `detail: "Experiment already has runs"`; a second GET of the run should still show the original snapshot. Launching another run is allowed and creates another distinct `QUEUED` record. These records stay queued until the MVP-04 worker is implemented; waiting or refreshing does not train them.

#### 4. Check validation and owner boundaries

While authorized as Alice, try separate **POST /api/v1/experiments** requests with these bodies. Each should return FastAPI `422` with a `detail` list and create no experiment:

```json
{"name":"Bad choice","algorithm":"other"}
{"name":"Too few clients","algorithm":"fedavg","n_clients":1}
{"name":"Wrong mu","algorithm":"fedavg","mu":0.3}
{"name":"Wrong type","algorithm":"fedprox","mu":true}
{"name":"User path","algorithm":"fedavg","dataset":"/tmp/other"}
```

Use **Authorize → Logout**, then log in as Bob and authorize his token. Bob's experiment list should be empty. Alice's experiment detail, edit, launch, and history URLs should each return `404`; Alice's run detail URL should also return `404`. A completely unknown UUID has the same `404` result. Log out in Swagger and request the experiment list again: expect `401`. This checks the API ownership boundary, not browser filtering.

#### 5. Run automated checks and stop local services

From `backend/`, with the optional runner installed and `FLUKE_TEST_ADMIN_URL` configured:

```sh
uv sync --locked --extra runner
uv run --locked --extra runner pytest -q -rs tests/test_experiments_api.py tests/test_database.py
uv run --locked --extra runner pytest -q -rs
uv run --locked --extra runner ruff check .
uv run --locked --extra runner ruff format --check .
uv run --locked --extra runner alembic check
uv build
```

The focused PostgreSQL check passed **10 tests** on 2026-10-08; the complete runner-enabled suite passed **74 tests** with no skips. Confirm your own summary: a skipped PostgreSQL test means `FLUKE_TEST_ADMIN_URL` was not configured, and a skipped runner test means the optional extra was not installed. [test_experiments_api.py](../backend/tests/test_experiments_api.py) checks defaults, edit, queued snapshot persistence, invalid forms, authentication, and cross-user `404`s. [test_database.py](../backend/tests/test_database.py) checks migration, downgrade/reapply, and schema readiness using disposable databases.

Stop Uvicorn with `Ctrl+C`. `docker compose down` stops PostgreSQL but retains accounts and experiments in its named volume. The Swagger token is cleared with **Authorize → Logout**; that does not revoke the signed JWT before its one-hour expiry.
