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
