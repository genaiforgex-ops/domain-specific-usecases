# Backend conventions (FastAPI + SQLAlchemy 2 + Pydantic v2 + Alembic)

All examples use a generic `Item` domain. When in doubt, open a matching existing
file (`app/api/<module>.py`, `app/models/<area>.py`, `app/schemas/<area>.py`) and
copy its shape.

## File & symbol naming

- Files: `snake_case.py`, named after the domain (`items.py`, `orders.py`).
- Classes: `PascalCase` (`Item`, `OrderLine`, `PaymentService`).
- Functions, variables, columns, JSON fields, query params: `snake_case`.
- API route prefixes: `kebab-case` matching the module (`/api/items`).
- Enums subclass `str, Enum` so values serialize cleanly.

## Imports — three groups, alphabetized within each

```python
"""Items module — one-line purpose."""               # module docstring first

from datetime import datetime, timezone               # 1. stdlib

from fastapi import APIRouter, Depends, HTTPException, Request, status   # 2. third-party
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user              # 3. first-party (app.*)
from app.database import get_db
from app.models.item import Item
from app.schemas.item import ItemOut
from app.services.item_service import process_item
```

- Every module gets a top docstring.
- Use modern typing: `list[dict]`, `str | None` — not `List`, `Optional`.
- Section dividers inside a file: `# ── Section title ─────────────────────────────`.

## Router (`app/api/<module>.py`)

```python
router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("", response_model=list[ItemSummary])
def list_items(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ItemSummary]:
    rows = db.execute(select(Item).order_by(Item.created_at.desc())).scalars().all()
    return [ItemSummary.model_validate(i) for i in rows]


@router.post("", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: ItemCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemOut:
    if not payload.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
    item = Item(name=payload.name, owner_id=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return ItemOut.model_validate(item)
```

Rules:
- **Always** declare both the parameter types and an explicit return type, and set
  `response_model`. Use `status.HTTP_*` constants, never bare integers.
- Validate inputs early and raise `HTTPException` with a clear `detail`.
- Keep business logic in a service; the router orchestrates and serializes.
- Register the new router in `app/main.py` via `app.include_router(<module>.router)`.

## Database access pattern (SQLAlchemy 2)

- Read many: `db.execute(select(Model).where(...).order_by(...)).scalars().all()`
- Read one by pk: `db.get(Model, id)` → check `is None` → raise 404.
- Write: `db.add(obj)`; `db.flush()` if you need the generated id before commit;
  `db.commit()`; then `db.refresh(obj)` before serializing.
- Cross-row ownership checks: e.g. `if line is None or line.order_id != order_id:`
- Use the request-scoped session from `Depends(get_db)`. Don't open ad-hoc sessions
  in request handlers (background loops use `SessionLocal()` directly — see `main.py`).

## Model (`app/models/<area>.py`)

```python
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Item(Base):
    """An item owned by a user."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lines: Mapped[list["ItemLine"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="ItemLine.order_index"
    )
```

Rules:
- Typed `Mapped[...] = mapped_column(...)`. Make nullability explicit on every column.
- Tables are `snake_case` plural; primary key is always `id`.
- Foreign keys: `ForeignKey("users.id")`; add `ondelete="CASCADE"` on child rows and
  `cascade="all, delete-orphan"` on the parent relationship when children are owned.
- Timestamps are timezone-aware: `DateTime(timezone=True)`; `created_at` uses
  `server_default=func.now()`.
- Use `JSON` columns for structured blobs.
- New model files must be imported in `app/models/__init__.py` so they register on
  the declarative `Base` (and so Alembic autogenerate sees them).

## Schema (`app/schemas/<area>.py`)

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ItemCreate(BaseModel):              # request body
    name: str
    kind: str = "default"


class ItemOut(BaseModel):                 # response — reads from the ORM object
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    name: str
    status: str
    score: float | None
    created_at: datetime
    lines: list[ItemLineOut] = []
```

Rules:
- Response/output schemas set `model_config = ConfigDict(from_attributes=True)` and are
  produced with `Schema.model_validate(orm_obj)`.
- Add `protected_namespaces=()` when a field starts with `model_` (e.g. `model_version`).
- Keep a `*Create` (input), `*Out` (full response), and `*Summary` (list view) split
  where the list and detail payloads differ.
- Inline `# allowed | values | here` comments document string-enum fields.

## Service (`app/services/<name>.py`)

- Services hold business logic and **all external seams** (LLM, storage, email).
- Wrap third-party SDKs behind an abstract interface; never call an SDK directly from
  a router. Select the concrete implementation via config (an env-driven setting),
  so the rest of the app is unchanged when a backend changes.
- Return plain `@dataclass` result types from services; keep them serialization-free.

## AI / LLM services

All AI lives behind one abstract interface so callers never touch a model SDK.

- **Interface**: an `AIService(ABC)` in `app/services/ai_service.py` with one
  `@abstractmethod` per capability. Each returns a `@dataclass` result that carries a
  `model_version` field. Callers always go through `get_ai_service()`, never a backend.
- **Backends**: subclasses implement the interface (`StubAIService`, `OllamaAIService`,
  `GeminiAIService`, `ADKAIService`, …). Ship a **deterministic stub** as the default
  so the app runs locally with no external dependency. Real backends should **fall back
  to the stub** on any failure rather than erroring the request.
- **Factory**: `get_ai_service()` returns a cached singleton chosen by the `AI_BACKEND`
  setting (`stub` | `ollama` | `gemini` | `adk` | …). Add a new backend as one `elif`
  branch here — the interface guarantees the rest of the app is unaffected.

### ADK (agent) backend — `app/adk/`

When a backend uses the Google Agent Development Kit, keep all ADK code in `app/adk/`
and keep orchestration (loading inputs, persisting results) in the service layer.

- `agents.py` — `build_*_agent()` factories returning single-purpose, **stateless**
  `LlmAgent`s bound to the configured model with a Pydantic `output_schema`. Setting
  `output_schema` disables tool use, which is the grounding guard: the agent reasons
  only over the text you hand it and cannot fetch outside sources.
- `runner.py` — a sync bridge (`asyncio.run(...)`) over ADK's async API, since the
  service interface and FastAPI `def` handlers are synchronous. One fresh in-memory
  session per call.
- `schemas.py` — the Pydantic `output_schema`s; `models.py` — `build_model()` from config.
- Use a low temperature for deterministic output; map the agent's structured result
  back into the service's `@dataclass` result type.

## Config (`app/config.py`)

- One `Settings(BaseSettings)` class, one module-level `settings = Settings()`.
- Add new config as a typed field with a safe local-dev default. Env var names are the
  upper-cased field names (`case_sensitive=False`). Never read `os.environ` elsewhere.

## Alembic migrations

The app never creates tables at runtime — schema is owned by `backend/alembic/versions/`.

Workflow after editing/adding a model:
```bash
cd backend
alembic revision --autogenerate -m "add item_revisions"   # generates a file
# REVIEW & edit the generated upgrade()/downgrade() — autogenerate is a draft
alembic upgrade head
```

Conventions:
- Filenames are timestamped: `YYYYMMDD_HHMM-<revision>_<slug>.py`.
- Every migration implements both `upgrade()` and `downgrade()`.
- Set `down_revision` to the previous head; keep the chain linear.
- Server defaults in migrations use `sa.text('(CURRENT_TIMESTAMP)')` for timestamps.
- Create indexes with `op.create_index(op.f('ix_<table>_<col>'), ...)` and drop them in
  `downgrade()`.
- For a pre-existing DB whose tables predate Alembic, baseline once with
  `alembic stamp head` instead of `upgrade`.

## Docker

- `backend/Dockerfile`: `python:3.12-slim`, installs `requirements.txt`, and its `CMD`
  runs `alembic upgrade head && uvicorn ...` so the container always migrates first.
- `docker compose up --build` builds and runs the services; the database connection is
  supplied through `DATABASE_URL` (env, never committed). Keep secrets in `.env`.
