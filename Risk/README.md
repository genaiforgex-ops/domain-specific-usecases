# GenAIForge Risk

AI-assisted risk showcase platform — outsourcing classification, vendor due diligence,
and enterprise risk scoring — for demonstrating GenAIForge production capabilities to clients.

## Stack

- **Frontend:** React 18, TypeScript, Vite
- **Backend:** FastAPI, SQLAlchemy 2, Alembic
- **Data:** PostgreSQL 16; local filesystem storage in Docker
- **AI:** Gemini (optional — set `GEMINI_API_KEY` in `.env`)

## Quick start (Docker)

```bash
cd Risk
cp .env.example .env   # already present if you copied .env
docker compose up --build
```

- Web UI: http://localhost:5174
- API docs: http://localhost:8002/docs

Sign in with any seed account (password from `SEED_PASSWORD`, default `demo1234`):

| Email | Role |
|-------|------|
| `admin@genaiforge.local` | admin |
| `manager@genaiforge.local` | user |
| `demo@genaiforge.local` | admin + user |

## Configuration

All settings load from [`.env`](.env) (see [`.env.example`](.env.example)).
There is no SSO and no cloud secret manager — email/password login only.

## Local (no Docker for app)

```bash
docker compose up -d postgres

cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=.
alembic upgrade head
uvicorn app.main:app --reload --port 8002
```

```bash
cd frontend && npm install && npm run dev -- --port 5174
```

## Tests

```bash
cd backend && PYTHONPATH=. pytest
cd frontend && npm test && npx tsc --noEmit
```
