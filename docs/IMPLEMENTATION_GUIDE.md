# Backend code walkthrough — completed tickets

This document explains **implemented code only**. As checked on **2026-10-07**, BE-01–04 and the MVP-01 auth simplification are complete. The [roadmap](TICKETS.md) remains the source for pending tickets and completion criteria; [BACKEND.md](BACKEND.md) describes the target architecture, [backend/README.md](../backend/README.md) contains runnable setup commands, and [CONTEXT.MD](../CONTEXT.MD) is the next-session handoff. Recheck source and tests if you read this after the snapshot date.

## Start with the part that runs now

The current backend can answer a health request, connect to a migrated PostgreSQL database, let an operator create an account, and let that user log in and inspect their identity. Client logout discards the token; there is no server logout route. It has no experiment table, run queue, worker, runner, Angular source, or FLUKE integration yet.

```text
Operator CLI ── create/reset/deactivate ─┐
                                        ▼
HTTP client ── login/me ── FastAPI ── PostgreSQL users
```

There are four useful layers to recognize. **Settings** reads and validates configuration. The **API** handles HTTP requests and responses. A **service** such as `AccountService` or `TokenService` contains the behavior. **Models** map Python objects to PostgreSQL rows. A **transaction** is the database boundary: its changes commit together, or roll back together if an error occurs. A **migration** changes the database schema; defining a SQLAlchemy model alone does not create its table.

To follow the existing code, start in `backend/` and read the linked files in each ticket section in order. The examples use fictional accounts. Never put a real password, JWT, or database URL in a committed file or shell history.

## Milestone A — Foundation and authentication (implemented)

Milestone A is the runnable foundation. Each subsection below follows one behavior through the actual source, explains why the boundary exists, and points to a test that proves it. The current code reflects later tickets too: for example, `Settings` now requires a JWT secret because BE-04 added one after BE-01.

### BE-01 — Reproducible backend setup

**What exists:** [pyproject.toml](../backend/pyproject.toml) declares Python 3.11, the `fluke-backend` package, base dependencies, and the `fluke-admin` entry point. [uv.lock](../backend/uv.lock) fixes the resolved dependency set so a fresh install does not silently choose newer versions. The optional `runner` extra is empty today: installing the API does not install FLUKE or PyTorch. [compose.yaml](../backend/compose.yaml) starts PostgreSQL 17, binds its port to `127.0.0.1`, and keeps data in a named volume. [`.env.example`](../backend/.env.example) lists variable names but contains no working credentials; the real `.env` is ignored by Git.

**Trace a request, step by step:**

1. `uvicorn fluke_backend.app:create_app --factory` imports [app.py](../backend/src/fluke_backend/app.py) and calls `create_app()`. Importing the module itself does not start PostgreSQL or load training libraries.
2. `create_app()` constructs [Settings](../backend/src/fluke_backend/settings.py). `BaseSettings` reads `FLUKE_` environment variables and the local `.env`; explicit environment variables take priority. `database_url` and `jwt_secret` are `SecretStr` values, so ordinary object representations hide them. Validators reject a non-PostgreSQL URL, a signing secret shorter than 32 characters, and malformed or wildcard development origins.
3. `create_app()` creates a `Database` object and registers routes. Creating the SQLAlchemy engine is lazy: it does not open a connection or create tables. The app's lifespan closes the engine pool when the app shuts down.
4. `GET /health/live` returns `{"status":"ok"}` without querying the database. It means the HTTP process is alive. It does **not** prove migrations or PostgreSQL are ready; BE-02 adds that distinction.

**Why these choices matter:** A machine may have a healthy API process while its database is down. A liveness endpoint that required PostgreSQL would blur those two failures. Keeping FLUKE out of the API install also keeps startup and simple tests lightweight.

**Follow it yourself:** Read `create_app()` and `liveness()` in [app.py](../backend/src/fluke_backend/app.py), then `Settings` in [settings.py](../backend/src/fluke_backend/settings.py). Run `uv run --locked pytest -q tests/test_app.py tests/test_settings.py` from `backend/`. The `test_import_and_liveness_do_not_connect_or_load_training_libraries` test deliberately rejects database connections and FLUKE/PyTorch imports; it proves the boundary rather than merely checking an HTTP status. For real startup commands, use [backend/README.md](../backend/README.md).

### BE-02 — Database lifecycle and migrations

**What exists:** [database.py](../backend/src/fluke_backend/database.py) creates a psycopg-backed SQLAlchemy engine and a transaction factory. [models.py](../backend/src/fluke_backend/auth/models.py) defines the `User` object-relational mapping (ORM) model: a Python object mapped to a database row. The first [Alembic migration](../backend/migrations/versions/20261006_0001_users_sessions.py) created `users` and `sessions`; the [MVP-01 migration](../backend/migrations/versions/20261007_0002_drop_sessions.py) removes `sessions` while retaining users. The current schema has `users` and `alembic_version`, with a unique email constraint, UUID keys, and timezone-aware timestamps. Alembic is the schema migration tool; defining an ORM model alone does not change PostgreSQL.

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

**Trace errors and browser access:** [app.py](../backend/src/fluke_backend/app.py) uses FastAPI's ordinary `detail` responses for HTTP and validation errors. `FLUKE_DEVELOPMENT_ORIGINS` configures exact allowed browser origins; the default list is empty. Cross-origin resource sharing (CORS) decides which browser origins may read responses. It does not authorize data access. There are no experiment or run endpoints yet; owner checks arrive with those resources.

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

If Colima is already running, skip `colima start`. Expect `20261007_0002 (head)` from `alembic current` and `No new upgrade operations detected` from `alembic check`. The current schema has `users` and `alembic_version`, not `sessions`. The automated migration test below proves that upgrading from the earlier revision preserves existing users and that downgrade/reapply works. Do **not** downgrade your application database to test that behavior.

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

The full PostgreSQL run currently has **45 passing tests**. Inspect the pytest summary: if integration tests are **skipped**, you have not verified database behavior. The upstream Starlette/HTTPX deprecation warning does not fail the suite. `ruff check` and `ruff format --check` should pass; Alembic should report no pending schema operations; `uv build` should produce a wheel and source distribution.

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

Stop Uvicorn with `Ctrl+C`. `docker compose down` stops PostgreSQL but retains its named volume. Avoid `docker compose down -v` if you want to keep local users. Milestone A ends here: experiment endpoints, FLUKE execution, a worker, and Angular are still future tickets.
