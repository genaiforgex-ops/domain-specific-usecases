# GenAIForge Marketing

Agentic campaign studio — a showcase platform for GenAIForge production AI capabilities (briefs, copy, creative, staged approvals).

## Quick start (Docker)

```bash
cd Marketing
cp backend/.env.example backend/.env   # already present if you cloned with .env
docker compose up --build
```

Open **http://localhost:5180** and sign in with any seed account (password from `SEED_PASSWORD`, default `demo1234`):

| Email | Role |
|-------|------|
| `cw@genaiforge.in` | Copywriter |
| `ml@genaiforge.in` | Marketing Lead |
| `pl@genaiforge.in` | Product Lead |
| `ds@genaiforge.in` | Designer |
| `admin@genaiforge.in` | Admin |

API docs: http://localhost:8000/docs

## Configuration

All secrets and settings load from [`backend/.env`](backend/.env) (see [`.env.example`](backend/.env.example)). There is no SSO or cloud secret manager in the local/demo path.

Optional: set `GEMINI_API_KEY` for AI brief/copy/image features.
