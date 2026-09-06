# GenAIForge Marketing — Backend

FastAPI + PostgreSQL. Email + password auth (JWT httpOnly cookie) for the five seeded role accounts.

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Postgres

```bash
createdb orchestration
# or via Docker Compose from the Marketing root
```

## Migrate & run

```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

On startup the app seeds missing role accounts (password = `SEED_PASSWORD`).

## Seed accounts

| Email | Role |
|-------|------|
| `cw@genaiforge.in` | CW — Copywriter |
| `ml@genaiforge.in` | ML — Marketing Lead |
| `pl@genaiforge.in` | PL — Product Lead |
| `ds@genaiforge.in` | DS — Designer |
| `admin@genaiforge.in` | AD — Admin |

## API

- `POST /api/auth/login` — `{ "email", "password" }` → session cookie + user
- `GET /api/auth/me` — current user
- `POST /api/auth/logout`
- `GET /health`
