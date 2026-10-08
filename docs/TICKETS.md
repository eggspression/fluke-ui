# FLUKE UI MVP tickets

This is the **active** roadmap for a 3–4 week university project. The goal is one understandable end-to-end demonstration: log in, configure FedAvg or FedProx on MNIST, save an experiment, run it on CPU, and inspect its status, logs, accuracy, and history in Angular. [BACKEND.md](BACKEND.md) defines the small technical contract. [CONTEXT.MD](../CONTEXT.MD) is the next-thread handoff.

BE-01–04 and MVP-01–03 are implemented; [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) explains the **current** code. The former BE-05–20 roadmap was superseded after Milestone B was reverted. Its implementation is not in the working tree. Git history retains it if needed, but it is not the MVP checklist.

Complete tickets in order. Check a box only after its behavior works, relevant tests pass, and this roadmap and the implementation guide reflect what actually shipped. Prefer a small function and a focused test over a framework of services or schemas for hypothetical future features. Run the backend suite and Ruff before marking a backend ticket done. No secrets, datasets, run logs, or generated models belong in Git.

## Completed foundation

- [x] **BE-01–04: backend setup, PostgreSQL, operator accounts, and authentication.** These are the original foundation tickets; MVP-01 below replaced their session behavior.

## MVP-01 — Simplify the existing authentication foundation

- [x] **Implemented and verified, 2026-10-07.** The local PostgreSQL suite passes all 45 tests; Ruff and the migration check pass. Continue with MVP-02.

Keep uv/Python 3.11, FastAPI, PostgreSQL, SQLAlchemy/Alembic, Argon2, and the operator account commands. Replace the database-backed session token with a signed, one-hour JWT containing the user ID and expiry. On every authenticated request, verify the signature/expiry and load the user to reject inactive accounts. The Angular logout action will discard the token; remove the server logout route and the sessions table through a new migration. Password reset does **not** revoke an already issued JWT; it expires within one hour. Keep create/reset/deactivate operator commands, but remove their session-revocation logic.

Remove the custom request-ID/error-envelope middleware and the tracked `backend/openapi.json`; use FastAPI's normal errors and generated `/openapi.json`. Keep explicit development CORS origins and health checks. Update tests and setup instructions to the new behavior. Existing users survive the migration; existing tokens do not. Do not refactor unrelated working code.

**Done when:** login, `/auth/me`, invalid/expired-token rejection, inactive-user rejection, account commands, migrations, health, and the full backend suite work. The code has one clear path for issuing a token and one for authenticating it. Update the BE-03/04 explanations in the implementation guide to match the new code.

## MVP-02 — Prove the FLUKE run before building management screens

- [x] **Implemented and verified, 2026-10-07.** The runner uses FLUKE revision `37c54630f0b4d9d6164f003cbed0811019acc5e1`, a 1% MNIST sample, and fresh CPU subprocesses. Two clients, two rounds, and one local epoch complete for both algorithms. Cached-dataset runs took 3.98 seconds (FedAvg) and 4.16 seconds (FedProx) on this Mac. Invalid configuration and deliberate dataset-path failure exit nonzero with a diagnostic log and no result. Continue with MVP-03.

Pin FLUKE to inspected revision `37c54630f0b4d9d6164f003cbed0811019acc5e1`. Build the smallest isolated runner using FLUKE's public construction and observer APIs, following its CLI as a reference without calling private `_run_federation()`. Prove two-round CPU runs for FedAvg and FedProx on a small MNIST sample, using `MNIST_2NN` and IID. Capture global accuracy for each round and a readable log. Use the same inputs the future worker will pass. FLUKE's CLI catches some exceptions, so a successful process exit alone cannot count as a successful experiment.

**Done when:** both algorithms finish from a fresh subprocess, the runner writes parseable round/accuracy results only after successful training, and deliberate invalid configuration or execution failure exits unsuccessfully with a diagnostic log. No HTTP or database work is required in this ticket.

## MVP-03 — Save owned experiments and run requests

- [x] **Implemented and verified, 2026-10-08.** Owned experiments and queued run snapshots work. The PostgreSQL and runner-enabled backend suite passed 74 tests; Ruff, build, and Alembic checks passed. Continue with MVP-04.

Add one small validated form schema: `algorithm` (`fedavg` or `fedprox`), `n_clients` (2–10, default 4), `n_rounds` (1–5, default 2), `local_epochs` (1–3, default 1), and positive FedProx `mu` (default 0.3; not accepted for FedAvg). Fix MNIST, IID, CPU, `MNIST_2NN`, seed 42, and a small MNIST sample in server-owned FLUKE templates; the proof ticket confirms the usable sample fraction. Do not create a generic catalog, separate validation endpoint, or user-selectable Python import/path fields.

Add `experiments` and `runs` tables with an Alembic migration. An experiment has owner, name, form configuration, and timestamps. A run has owner, experiment, a **copy** of its configuration, status (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`), timestamps, and a short failure message. Provide owned create/list/get experiments and basic edit while the experiment has **no** runs. A later edit returns `409`; create another experiment instead. Provide run launch, owned run detail, and per-experiment run history. The launch request only commits a `QUEUED` row; it does not train in FastAPI.

**Done when:** the API rejects invalid choices and cross-user access, edits are blocked once any run exists, and a run snapshot stays unchanged. API responses use FastAPI's normal validation errors. No revision locks, archives, reruns, idempotency keys, export, or cursor pagination.

## MVP-04 — Run one queued job through a tiny local worker

- [ ] **Not started.**

Add one worker command started beside the API. It picks the oldest `QUEUED` run, marks it `RUNNING`, creates a server-owned directory using the run ID, and starts MVP-02's runner as a fresh subprocess. Capture stdout/stderr in a log file. Keep API secrets and database credentials out of the runner environment. Mark `COMPLETED` only when the subprocess exits successfully **and** its result file is valid; otherwise mark `FAILED` with a safe reason. The worker runs one job at a time. The API exposes owned run status/accuracy and a bounded recent-log read; no generic event bus or JSONL ingestion layer is needed.

**Done when:** a queued run becomes completed with per-round accuracy, a deliberate runner failure becomes failed with a readable log, logs can be read while running, and another user cannot inspect either. Worker/machine crash recovery and automatic cancellation are outside this MVP. If the worker starts with an unresolved `RUNNING` row, it must stop with a clear operator message rather than launch another job blindly; document the manual recovery limitation.

## MVP-05 — Build the minimal Angular flow

- [ ] **Not started.**

Create only the screens required for the demonstration: login; experiment list and create/edit form; experiment detail with run history and launch; run detail with status, recent logs, and a per-round accuracy chart or table. Keep the token in memory and clear it on logout. Poll an active run roughly every two seconds. Show invalid form fields and failed-run messages plainly. Keep the UI choices consistent with the small API schema; do not build a dynamic form generator.

**Done when:** a user can complete the entire flow without curl or the operator CLI after their account has been created. The UI neither imports FLUKE nor reads run files directly. A second user sees only their own records.

## MVP-06 — End-to-end proof and handoff

- [ ] **Not started.**

Run the full workflow against local PostgreSQL and the pinned FLUKE runtime: create two users, log in, save FedAvg and FedProx experiments, launch a two-round CPU run of each, see accuracy/logs/history, and verify cross-user denial. Exercise one invalid form and one deliberate failed run. Run backend tests, Ruff, migration checks, and a frontend build. Write a short setup/demo guide with exact commands for PostgreSQL, API, worker, and Angular. Keep [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) limited to code actually implemented.

**Done when:** another student can follow the guide on a prepared machine and reproduce the demo. Record any dataset download, runtime, or platform limitation honestly.

## Delivery order and scope guard

| Time | Main goal | Visible result |
|---|---|---|
| Week 1 | MVP-01 and MVP-02 | Simpler auth and two real subprocess FLUKE proofs |
| Week 2 | MVP-03 and MVP-04 | Authenticated API can save and run experiments |
| Week 3 | MVP-05 | Angular demonstrates the workflow |
| Week 4, if available | MVP-06 and fixes | Repeatable demo and clean handoff |

The grading rubric is still unclear. Until it says otherwise, defer cancellation, CUDA, Fashion-MNIST, Dirichlet, model downloads, configuration export, reruns, distributed workers, detailed crash recovery, and production deployment. If a rubric requirement conflicts with this list, update the MVP scope **before** implementing that feature.
