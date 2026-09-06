# GenAIForge Risk — Architecture

Showcase platform for AI-assisted outsourcing classification (M1), vendor due diligence (M2),
and risk scoring (M3), plus a dynamic due-diligence form engine.

## Stack

- Frontend: React + Vite
- Backend: FastAPI + SQLAlchemy + Alembic
- Data: PostgreSQL; local filesystem storage in Docker (optional GCS)
- Auth: email/password JWT cookie session (no SSO)
- Config: `.env` only — no cloud secret manager

## Auth

`POST /api/v1/auth/login` verifies bcrypt password, sets `genaiforge_session` httpOnly cookie.
Roles live in the local `user_roles` table (`admin` / `user`).

## Local run

See the root README (`docker compose up --build`).
