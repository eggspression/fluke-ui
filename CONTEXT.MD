# FLUKE UI — next-thread handoff

Checked on **2026-10-08**. This file distinguishes what exists from the newly agreed MVP plan. Recheck `git status`, source, and tests at the start of a new thread; this handoff does not override the current user's instructions.

## What the user wants

This is a **3–4 week university MVP**, not a production platform. The user explicitly found the former 20-ticket roadmap and reverted Milestone B overengineered. They want code that is clear enough to read and explain, with a complete small demo rather than many abstractions and edge-case systems. The grading rubric is still unclear, so treat the chosen scope below as the working default and revise it only for actual rubric requirements.

The agreed demo: Angular login; save and, before its first run, edit an owned experiment; choose **FedAvg or FedProx on MNIST/CPU** with a few numeric controls; launch through a tiny local worker into a fresh FLUKE subprocess; poll status and logs; show accuracy per round and run history. A second user cannot read the first user's data. Show ordinary invalid-input and runner failures. No model download is required.

The user chose to **simplify Milestone A first**. MVP-01 now uses one-hour stateless JWTs. Angular logout will discard the token; immediate server-side revocation is not required. The operator account commands remain. The user also chose a **tiny separate worker** instead of launching training inside FastAPI.

## Repository truth today

Milestone A (BE-01–04) and MVP-01–03 are implemented. The package uses uv/Python 3.11, FastAPI, PostgreSQL 17, SQLAlchemy/Alembic, Argon2, and one-hour signed JWTs. It serves health and login/current-user routes. A separate optional runner executes real FLUKE FedAvg and FedProx CPU runs from JSON snapshots. Owned experiment and run tables/API exist; launch stores `QUEUED` run snapshots only. There is no worker or Angular app. The sessions table and `/auth/logout` route have been removed by a migration; `backend/openapi.json` is no longer tracked.

Milestone B's previous implementation was reverted in commit `41084e2`; the active MVP does not reuse its catalog/experiment subsystem. The local database is at `20261008_0003`. The MVP-03 check passed **74 tests** with PostgreSQL and the optional FLUKE runner installed, plus Ruff, package build, and Alembic metadata comparison. FedAvg and FedProx each completed two rounds using two clients, one local epoch, and `sampling_perc: 0.01`; cached-data runs took 3.98 and 4.16 seconds on this Mac. The first real run downloaded approximately 64 MB of MNIST data. Treat timing and test counts as dated evidence, not a future guarantee.

The local `local/docs` branch tracks documentation and remains unpushed. `backend/.env` contains ignored local secrets; never print, commit, or copy its values into documentation.

## Active documents

1. [MVP tickets](docs/TICKETS.md) — the six-ticket active checklist and order. **MVP-04 is next.** The old BE-05–20 ticket plan is superseded, not implemented.
2. [Backend design](docs/BACKEND.md) — exact small form, API, data flow, worker, and failure rules.
3. [System overview](docs/SYSTEM_OVERVIEW.md) — short user journey and success criteria.
4. [Implementation guide](docs/IMPLEMENTATION_GUIDE.md) — detailed explanation of **currently shipped** BE-01–04 and MVP-01–03 code.
5. [Backend setup](backend/README.md) — commands that work for today's code; update them with each implemented slice.

The pinned FLUKE checkout is `../fluke` at revision `37c54630f0b4d9d6164f003cbed0811019acc5e1`. Its process-wide `FlukeENV` is why every run gets a subprocess. The new runner uses public construction and observer APIs, never private `_run_federation()`. It requires the requested number of completed rounds and finite global accuracy before writing `result.json`; it writes a diagnostic `run.log` even for ordinary failures. Keep this simple contract for the worker.

## Exact next action: MVP-04 only

Read the MVP-04 pass requirements. Add one local worker command that reads the oldest `QUEUED` run, marks it `RUNNING`, and launches the proven runner in a fresh subprocess. Keep secrets out of its environment. Validate exit status and result file before marking `COMPLETED`; otherwise store `FAILED` with a safe reason. Add owned status/accuracy and recent-log reads. Do not add automatic recovery or distributed machinery.

MVP-01 changed existing behavior: user records survive migration, old login tokens are invalid, and password reset no longer revokes a token already issued. Account deactivation still blocks authenticated requests. Verify the local database is at `20261008_0003` before serving API traffic.

## Working rhythm and limits

From `backend/`: `uv sync --locked`, `docker compose up -d --wait postgres`, `uv run --locked alembic upgrade head`, `uv run --locked pytest -q`, `uv run --locked ruff check .`, and `uv run --locked ruff format --check .`. Add `--extra runner` to install and test FLUKE; direct runner commands are in `backend/README.md`. Database tests use disposable local PostgreSQL when `FLUKE_TEST_ADMIN_URL` is configured; confirm they ran rather than skipped.

Proceed ticket by ticket. Prefer one understandable module per real responsibility and tests of behavior rather than scaffolding for imagined features. Update the implementation guide with **what has been implemented**, with code traces and examples, only after a ticket is verified. No cancellation, CUDA, extra datasets, export, rerun, complex event protocol, or automated crash recovery unless the grading rubric requires it.
