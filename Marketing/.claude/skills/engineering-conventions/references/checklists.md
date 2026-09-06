# End-to-end checklists

Concrete, ordered steps for the common changes. Follow them top to bottom.

## Add a new API endpoint to an existing module

1. **Schema** — add the request/response models in `app/schemas/<area>.py`
   (`*Create` for the body, `*Out`/`*Summary` for responses; `ConfigDict(from_attributes=True)`).
2. **Route** — add the handler in `app/api/<module>.py`:
   validate input, do the work (delegating logic to a service), then
   `db.commit()` / `db.refresh()` and return `Schema.model_validate(obj)`.
3. **Client** — add a method to the `api` object in `frontend/src/lib/api.ts` and any new
   interface to `frontend/src/types/index.ts`.
4. **Use it** in the relevant page/component.

## Add a new model / table

1. Create or extend `app/models/<area>.py` (typed `Mapped` columns, FKs with `ondelete`,
   timezone-aware `created_at`, relationships with `back_populates`).
2. Import the new model in `app/models/__init__.py` so it registers on `Base`.
3. Generate the migration:
   `cd backend && alembic revision --autogenerate -m "describe change"`.
4. **Review and hand-correct** the generated `upgrade()`/`downgrade()` — autogenerate is a
   draft (it misses some server defaults, enum changes, data backfills).
5. `alembic upgrade head` to apply locally; confirm with `alembic current`.
6. Add matching Pydantic schemas and (if exposed) API + frontend types.

## Add a column to an existing table

1. Add the `mapped_column(...)` to the model with explicit nullability/default.
2. `alembic revision --autogenerate -m "add <col> to <table>"`, review, `upgrade head`.
3. If the column is non-nullable on an existing table, give it a `server_default` (or
   backfill in the migration) so existing rows are valid.
4. Surface it in the relevant `*Out`/`*Summary` schema and frontend type if needed.

## Add a whole new module

1. `app/models/<module>.py` → models (+ register in `models/__init__.py`).
2. `app/schemas/<module>.py` → DTOs.
3. `app/services/<module>_service.py` → business logic / external seams (if non-trivial).
4. `app/api/<module>.py` → `APIRouter(prefix="/api/<kebab-module>", tags=["<kebab-module>"])`.
5. `app/main.py` → `app.include_router(<module>.router)`.
6. Alembic migration for the new tables; `upgrade head`.
7. Frontend: `lib/api.ts` methods, `types/index.ts` interfaces, a `pages/<Module>.tsx`,
   and a route in `App.tsx`.
8. Update `README.md` if the module is user-facing.

## Add a new AI capability

1. Add the abstract method + a `@dataclass` result type (with `model_version`) to the
   `AIService` interface in `app/services/ai_service.py`.
2. Implement it in the deterministic `StubAIService` (so local dev works with no model)
   and in each real backend; real backends fall back to the stub on failure.
3. For an ADK backend: add the agent factory + Pydantic `output_schema` in `app/adk/`,
   run it via the sync runner, and map the structured result to the `@dataclass`.
4. Call it from the service/route via `get_ai_service()` — never a model SDK directly.

## Add a config value

1. Add a typed field with a safe local default to `Settings` in `app/config.py`.
2. Reference it as `settings.<field>` — never read env vars elsewhere.
3. Document it in `.env.example` (and add to `docker-compose.yml` env if the container
   needs it).

## Before opening a PR

- [ ] Schema change has a reviewed Alembic migration with a working `downgrade()`.
- [ ] No ORM objects leak across the API boundary (return `*Out` schemas).
- [ ] No secrets committed; new env vars are in `.env.example`.
- [ ] `docker compose up --build` boots (backend migrates, both services serve).
