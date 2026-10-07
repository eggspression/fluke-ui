# FLUKE UI — next-thread handoff

Checked on **2026-10-07**. This file distinguishes what exists from the newly agreed MVP plan. Recheck `git status`, source, and tests at the start of a new thread; this handoff does not override the current user's instructions.

## What the user wants

This is a **3–4 week university MVP**, not a production platform. The user explicitly found the former 20-ticket roadmap and reverted Milestone B overengineered. They want code that is clear enough to read and explain, with a complete small demo rather than many abstractions and edge-case systems. The grading rubric is still unclear, so treat the chosen scope below as the working default and revise it only for actual rubric requirements.

The agreed demo: Angular login; save and, before its first run, edit an owned experiment; choose **FedAvg or FedProx on MNIST/CPU** with a few numeric controls; launch through a tiny local worker into a fresh FLUKE subprocess; poll status and logs; show accuracy per round and run history. A second user cannot read the first user's data. Show ordinary invalid-input and runner failures. No model download is required.

The user chose to **simplify Milestone A first**. MVP-01 now uses one-hour stateless JWTs. Angular logout will discard the token; immediate server-side revocation is not required. The operator account commands remain. The user also chose a **tiny separate worker** instead of launching training inside FastAPI.

## Repository truth today

Milestone A (BE-01–04) plus MVP-01 are implemented. The package uses uv/Python 3.11, FastAPI, PostgreSQL 17, SQLAlchemy/Alembic, Argon2, and one-hour signed JWTs. It serves health and login/current-user routes. There is **no** experiment table/API, worker, runner, Angular app, or real FLUKE integration. The sessions table and `/auth/logout` route have been removed by a new migration; `backend/openapi.json` is no longer tracked.

Milestone B's previous implementation was reverted on local `main` in commit `41084e2`; its tracked tree matched the pre-BE-05 commit. The local database was at `20261006_0001` before MVP-01 and is upgraded to `20261007_0002` for the simpler auth schema. The latest full MVP-01 check passed **45 tests**, Ruff, and Alembic metadata comparison. Treat that as dated evidence, not a future guarantee.

Two pre-existing untracked files, `docs/AGENTS.md` and `docs/superpowers/plans/2026-10-05-be-01.md`, were left untouched. Do not overwrite them. `backend/.env` contains ignored local secrets; never print, commit, or copy its values into documentation.

## Active documents

1. [MVP tickets](docs/TICKETS.md) — the six-ticket active checklist and order. **MVP-02 is next.** The old BE-05–20 ticket plan is superseded, not implemented.
2. [Backend design](docs/BACKEND.md) — exact small form, API, data flow, worker, and failure rules.
3. [System overview](docs/SYSTEM_OVERVIEW.md) — short user journey and success criteria.
4. [Implementation guide](docs/IMPLEMENTATION_GUIDE.md) — detailed explanation of **currently shipped** BE-01–04 and MVP-01 code.
5. [Backend setup](backend/README.md) — commands that work for today's code; update them with each implemented slice.

The pinned FLUKE checkout is `../fluke` at revision `37c54630f0b4d9d6164f003cbed0811019acc5e1`. Its process-wide `FlukeENV` is why every run gets a subprocess. Its CLI federation path catches some exceptions, so a plain exit code is not enough proof of a successful run. Its basic `Log.save()` writes metric history explicitly; `Log.close()` alone does not. Use these findings without rebuilding the old event/recovery platform.

## Exact next action: MVP-02 only

Read the MVP-02 pass requirements and the pinned FLUKE checkout. Prove two-round CPU FedAvg and FedProx runs on a small MNIST sample from a fresh subprocess, writing parseable per-round accuracy only after successful training. Keep the proof independent of HTTP and database. Record the working sample fraction and any dataset download/runtime limitation. Stop and report a concrete blocker if either algorithm cannot complete; do not build experiment management around an unproved runner.

MVP-01 changed existing behavior: user records survive migration, old login tokens are invalid, and password reset no longer revokes a token already issued. Account deactivation still blocks authenticated requests. Verify the local database is at `20261007_0002` before serving API traffic.

## Working rhythm and limits

From `backend/`: `uv sync --locked`, `docker compose up -d --wait postgres`, `uv run --locked alembic upgrade head`, `uv run --locked pytest -q`, `uv run --locked ruff check .`, and `uv run --locked ruff format --check .`. Database tests use disposable local PostgreSQL when `FLUKE_TEST_ADMIN_URL` is configured; confirm they ran rather than skipped.

Proceed ticket by ticket. Prefer one understandable module per real responsibility and tests of behavior rather than scaffolding for imagined features. Update the implementation guide with **what has been implemented**, with code traces and examples, only after a ticket is verified. No cancellation, CUDA, extra datasets, export, rerun, complex event protocol, or automated crash recovery unless the grading rubric requires it. If the FLUKE proof cannot run both algorithms, report the concrete blocker before building management features around an assumption.
