# FLUKE UI backend — small MVP design

**Planning status, 2026-10-07:** This is the target for the 3–4 week university MVP, not a claim that all these features exist. BE-01–04 and the MVP-01 auth simplification are implemented today. See [TICKETS.md](TICKETS.md) for work order, [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) for shipped code, and [CONTEXT.MD](../CONTEXT.MD) for a new-thread handoff.

## What the demo must do

An operator creates an account. The user logs in through Angular, saves a FedAvg or FedProx experiment on MNIST, launches a CPU run, watches its status and log, and sees accuracy by round and past runs. A second user's data stays private. A bad form or failed FLUKE run has a visible error. That is the working product; extra knobs and operational machinery are not part of the first version.

```text
Angular ──HTTP──> FastAPI ──transactions──> PostgreSQL
                    │                         ▲
                    │ creates QUEUED run      │ reads/updates run
                    └──────────────────> one local worker
                                           │ launches fresh subprocess
                                           ▼
                                         FLUKE
                                           │
                                  log + accuracy result files
```

FastAPI never performs training in a request. The worker executes one queued job at a time. Each job uses a fresh subprocess because FLUKE keeps process-wide state. Only the runner imports FLUKE and PyTorch. The frontend reads state through the API, never from the filesystem.

## Implemented authentication

Keep operator-created users, Argon2 hashes, and signed JWTs. A token lasts one hour and identifies a user, without a separate session row. Every protected request verifies the token and loads the user to check that the account is active. Angular keeps the token in memory and discards it on logout. Password reset does not revoke a token already issued; it expires within one hour. Remove the server logout route and the sessions table in a migration; existing user records remain. Use FastAPI's ordinary HTTP/validation errors. Keep exact development CORS origins and `/health/live` and `/health/ready`.

This simpler design is implemented. The migration drops `sessions` and preserves `users`; tokens issued by the older session-based design are rejected.

## Configuration and persistence

The UI form and API accept a deliberately small configuration:

| Field | MVP rule |
|---|---|
| `algorithm` | `fedavg` or `fedprox` |
| `n_clients` | integer 2–10, default 4 |
| `n_rounds` | integer 1–5, default 2 |
| `local_epochs` | integer 1–3, default 1 |
| `mu` | positive number for FedProx, default 0.3; rejected for FedAvg |

The server maps these values through two readable FLUKE templates. Dataset MNIST, IID distribution, `MNIST_2NN`, CPU, seed 42, and participation fraction 1.0 are fixed. Use a small real MNIST sample so a two-round demonstration completes promptly; MVP-02 determines and records a proven sample fraction. Dataset paths, logger names, output locations, and Python import strings are never accepted from a request. There is no generic catalog registry or separate validation endpoint. The FastAPI request model validates the form when an experiment is saved.

An experiment stores its owner, name, configuration, and timestamps. It can be edited until its first run is created. Once a run exists, a `PATCH` returns `409`, so earlier work stays understandable. Each run stores a copy of the configuration, experiment/owner IDs, status, timestamps, and a short failure message. Store logs and metrics in a run directory selected from the server-generated run ID. Do not store absolute user-supplied paths in the database.

## Small HTTP contract

Keep the `/api/v1` prefix. Planned endpoints:

| Route | Purpose |
|---|---|
| `POST /auth/login`, `GET /auth/me` | Login and current user |
| `GET/POST /experiments`, `GET/PATCH /experiments/{id}` | Owned configurations; edits only before first run |
| `POST /experiments/{id}/runs` | Save a `QUEUED` run snapshot; return `202` |
| `GET /experiments/{id}/runs`, `GET /runs/{id}` | Owned history, status, failure, and available per-round accuracy |
| `GET /runs/{id}/logs` | Bounded recent diagnostic text, including during a run |

All experiment/run/log lookups filter by the authenticated owner. Missing or someone else's resource returns `404`. A supplied configuration is a complete replacement on edit, not a nested merge. Lists can be simple newest-first arrays for this local MVP; add pagination only if real data volume requires it. Let FastAPI generate `/openapi.json` at runtime instead of committing a large snapshot.

## Runner and failure rules

Pin the FLUKE integration to revision `37c54630f0b4d9d6164f003cbed0811019acc5e1`. Follow its public construction and observer APIs; do not call private `_run_federation()`. The existing CLI catches some exceptions, so its exit code alone is not a valid success signal. The runner explicitly writes a small result file with round/accuracy values only after all requested rounds complete. The worker marks completion only if the runner exits zero **and** that file parses and shows the expected rounds. Capture stdout and stderr as a log; do not parse console text for metrics. On ordinary initialization/training/result-write failure, retain the log and mark `FAILED`.

The worker is a single local process. It commits state before waiting for training, so PostgreSQL transactions do not span a run. It passes a minimal environment to the runner without JWT or database credentials. On startup, an unresolved `RUNNING` row is an operator-visible stop condition; the MVP does not automatically signal unknown processes or resume a crashed worker. This is a known local-demo limitation, not a hidden recovery promise.

## Explicitly deferred

No cancellation, CUDA, additional datasets/distributions, model download, configuration ZIP export, rerun endpoint, event protocol, idempotency keys, cursor pagination, distributed workers, automatic retry, or production crash recovery. The grading rubric is not yet confirmed; revisit only requirements it actually mandates. Keep code grouped by real responsibility, but do not create a separate layer or file for a one-line delegation.
