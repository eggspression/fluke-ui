# FLUKE UI — MVP overview

**Planning status, 2026-10-08:** This describes the intended university-project demo. The repository currently implements backend setup, PostgreSQL, operator accounts, simplified one-hour JWT authentication, and a separate FLUKE subprocess runner proven with FedAvg and FedProx on sampled MNIST. Owned experiments and queued run records are implemented; the worker and Angular remain planned. See [TICKETS.md](TICKETS.md) for the active six-ticket roadmap and [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) for behavior that exists today.

## Purpose

FLUKE already runs federated-learning experiments. This project adds a small web interface so a user can save a configuration, start a local run, and inspect its outcome without manually preparing YAML and searching terminal output. It does not reimplement training.

The first demo uses Angular, FastAPI, PostgreSQL, one local worker, and FLUKE in a fresh subprocess. It supports **FedAvg and FedProx on MNIST with CPU and IID data**. The user chooses the algorithm and a few training values; the backend controls all paths and other FLUKE settings.

## User journey

1. An operator creates an account with the backend command. The user logs in through Angular. The browser holds a short-lived token in memory and discards it on logout.
2. The user creates an experiment with a name, algorithm, client count, round count, local epochs, and FedProx `mu` when relevant. They may edit it until they start its first run; afterward they create a new experiment to try different settings.
3. The user launches a run. The API saves a `QUEUED` run with a copy of the configuration and returns promptly. The one local worker starts a fresh FLUKE subprocess and changes status to `RUNNING`.
4. Angular polls the API for status and recent logs. On completion it shows accuracy by round. The experiment page shows past runs. A failed run shows a concise reason and its log.
5. Users can access only their own experiments, runs, accuracy, and logs. The API performs ownership checks; Angular's filtering is only presentation.

```text
User → Angular → FastAPI → PostgreSQL run record
                    ↑                 ↓
              status/logs       local worker → FLUKE subprocess
                                   ↓
                           log and accuracy files
```

## What counts as the MVP

A local demonstration must complete two small CPU runs, one for each algorithm, display their status/logs/per-round accuracy, retain their history, and reject a second user's access. An invalid configuration and a deliberate runner failure must be understandable in the UI. The setup guide must let another student start PostgreSQL, the API, worker, and Angular and repeat the demonstration.

This is a **local university MVP**, not a production service. Worker crashes during training need manual investigation; cancellation, GPU support, multiple datasets, model downloads, export, and deployment/backup automation are deferred unless the grading rubric requires them. The rubric has not yet been confirmed.

## Where to read next

- [MVP tickets](TICKETS.md): implementation order and acceptance checks.
- [Backend design](BACKEND.md): exact configuration, API, worker, and failure boundaries.
- [Implementation guide](IMPLEMENTATION_GUIDE.md): explanations of currently shipped code only.
- [Next-thread context](../CONTEXT.MD): current repository state and the first action to take.
