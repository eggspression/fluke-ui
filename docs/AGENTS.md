# Repository Guidelines

## Project Structure & Module Organization

This repository contains architecture documents, the backend authentication foundation, owned experiments and queued runs, and an isolated FLUKE runner. `SYSTEM_OVERVIEW.md` defines the planned FLUKE web management platform's three boundaries: an Angular frontend, a backend API, and the external FLUKE execution framework. `BACKEND.md` and `TICKETS.md` specify the active MVP scope.

As implementation is added, keep these concerns in separate top-level directories (for example, `frontend/` and `backend/`). Place tests beside their owning module or in a clearly named `tests/` directory, and keep generated run logs, metrics, model outputs, and secrets out of version control. Add component-specific documentation such as `FRONTEND.md` or `BACKEND.md` when design detail no longer belongs in the system overview.

## Build, Test, and Development Commands

The backend uses uv and Python 3.11. See [backend setup](../backend/README.md) for environment configuration. From `backend/`:

- `uv sync --locked` — install the project and development tools.
- `uv sync --locked --extra runner` — include the pinned FLUKE/PyTorch stack for MVP-02 CPU proofs.
- `docker compose up -d --wait postgres` — start PostgreSQL 17 with persistent storage.
- `uv run --locked uvicorn fluke_backend.app:create_app --factory --reload` — start the API.
- `uv run --locked pytest` — execute backend tests.
- `uv run --locked ruff check .` — lint Python code.
- `uv run --locked ruff format --check .` — check formatting.

The frontend has no manifest or build/test commands yet.

Run `rg --files` to review tracked project files and `rg "term"` for repository-wide searches.

## Coding Style & Naming Conventions

Follow the formatter and linter configured within each component; commit their configuration with the first implementation. Use two-space indentation for Angular/TypeScript and four spaces for Python. Name Angular files with kebab-case and role suffixes (`experiment-list.component.ts`, `run.service.ts`). Use `PascalCase` for types/classes, `camelCase` for TypeScript values, and `snake_case` for Python modules and functions. Keep HTTP handlers thin; business logic and FLUKE integration belong in dedicated services.

## Testing Guidelines

Add tests with every behavior change. Cover authorization boundaries, experiment validation, run lifecycle transitions, and failure reporting as those features are added. Cancellation is outside the current MVP. Name tests after observable behavior (for example, `test_user_cannot_read_another_users_run`). No numeric coverage threshold is configured.

## Commit & Pull Request Guidelines

The repository uses short ticket branches and concise Conventional Commit subjects. Keep `main` working and retain local documentation on `local/docs` without pushing it. Pull requests should explain the change, testing performed, and architectural impact; include screenshots for visible UI changes. Never commit credentials, JWT secrets, local environment files, or generated FLUKE artifacts.
