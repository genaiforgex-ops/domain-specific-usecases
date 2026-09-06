---
name: engineering-conventions
description: >-
  Stack-general code structure, layering, and naming conventions for a
  FastAPI + SQLAlchemy 2 + Pydantic v2 + Alembic backend and a
  React 18 + TypeScript + Vite + Tailwind frontend. Use this whenever you add or
  modify code in such a project — a new API endpoint, ORM model, Pydantic schema,
  migration, service, or React page — so contributions stay consistent. For
  general coding behavior (think before coding, simplicity, surgical changes,
  goal-driven execution), see the coding-guidelines skill.
---

# Engineering conventions

How to write and structure code in a FastAPI + SQLAlchemy + React project so any
contribution stays consistent with what already exists. When a rule here conflicts
with a habit from another codebase, the rule here wins.

## Recommended stack

| Layer             | Technology                                  | Notes |
| ----------------- | ------------------------------------------- | ----- |
| Database          | **PostgreSQL**                              | Reached via `DATABASE_URL`; never hard-code connection strings. |
| API framework     | **FastAPI** (`app.main:app`)                | One router per module, registered in `main.py`. |
| ORM               | **SQLAlchemy 2** (typed `Mapped[...]`)      | Declarative `Base` in `app/database.py`. |
| Validation/DTOs   | **Pydantic v2** (+ `pydantic-settings`)     | Request/response schemas only — never expose ORM objects directly. |
| Schema migrations | **Alembic**                                 | The app does **not** auto-create tables. Schema is owned by migrations. |
| Containerization  | **Docker** + Docker Compose                 | Backend image runs `alembic upgrade head` before serving. |
| Frontend          | **React 18 + TypeScript + Vite + Tailwind** | Centralized typed API client; UI primitives under `components/ui`. |

Pin new dependencies with exact `==` versions in `backend/requirements.txt`, matching
the existing style.

## Repository layout (where code goes)

```
backend/app/
  main.py            FastAPI entry: CORS, router registration, lifespan startup
  config.py          Pydantic settings — the ONLY place that reads env vars
  database.py        engine + SessionLocal + Base + get_db()
  core/              cross-cutting concerns (security/auth, shared helpers)
  models/            SQLAlchemy ORM models — one file per domain area
  schemas/           Pydantic request/response DTOs — one file per domain area
  api/               FastAPI routers — one file per module, plus deps.py
  services/          business logic / external seams (LLM, storage, email, …)
backend/alembic/versions/   timestamped migration files

frontend/src/
  main.tsx           React entry + router
  App.tsx            route tree
  lib/               api.ts (typed client), utils.ts
  components/        shared components; components/ui/ = styled primitives
  contexts/          React contexts
  pages/             one page per module
  types/index.ts     TypeScript interfaces mirroring backend schemas
```

The dependency direction is strict: `api → services → models`, with `schemas` as the
boundary types and `core`/`config`/`database` as shared foundations. A router never
contains business logic that belongs in a service; a model never imports a schema.

## Golden rules

1. **Layer everything.** Routers parse/authorize/respond. Services hold logic and
   own the seams to external systems (LLM/storage/email). Models are persistence
   only. Schemas are the wire contract. Never collapse these.
2. **Schema changes go through Alembic.** Edit the model, then
   `alembic revision --autogenerate -m "..."`, then review and edit the generated
   file. Never hand-edit a shipped migration; add a new one.
3. **`config.py` is the only reader of environment variables.** Everything else
   imports `settings`.
4. **Pydantic DTOs cross the boundary, ORM objects never do.** Return
   `SomeSchema.model_validate(orm_obj)`.
5. **External systems live behind a service interface**, never called directly from
   a router. Swap implementations via config, not by editing call sites.

## Detailed references

Read the relevant reference before writing code in that area:

- **Backend conventions & copy-paste templates** → [references/backend.md](references/backend.md)
  (router, model, schema, service, AI/agent (ADK) services, migration, naming, imports, errors)
- **Frontend conventions** → [references/frontend.md](references/frontend.md)
  (API client, types, UI primitives, pages, Tailwind styling)
- **End-to-end checklists** → [references/checklists.md](references/checklists.md)
  ("add a new module", "add an endpoint", "add a column", "add a migration")

## Quick commands

```bash
# Backend (from backend/)
alembic upgrade head                                   # apply migrations
alembic revision --autogenerate -m "describe change"   # create migration after model edit
uvicorn app.main:app --reload --port 8000

# Whole app
docker compose up --build      # backend migrates, then backend + frontend start

# Frontend (from frontend/)
npm run dev
```
