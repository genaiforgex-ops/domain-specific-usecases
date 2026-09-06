# LegalOS — JFPSL Legal AI Central Platform

Internal scaffold implementing the BRD v1.0 (May 2025) for the Corporate Legal function at Jio Finance Platform Ltd.

Six AI-powered modules behind a single React frontend, FastAPI backend, PostgreSQL store, and pluggable AI service:

| ID    | Module                                  | Replaces            |
| ----- | --------------------------------------- | ------------------- |
| UC-01 | Contract Review (clause-level + risk)   | SpotDraft           |
| UC-02 | Document Comparison (V1 vs V2 diff)     | SpotDraft           |
| UC-03 | LegalBot (Tier-1 internal queries)      | manual handling     |
| UC-04 | Legal Research (RAG over reg corpus)    | Lucio               |
| UC-05 | MSA / NDA Automation (Gmail-integrated) | SpotDraft + email   |
| UC-06 | Legal News & Regulatory Monitoring      | Lucio               |

## Stack

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS
- **Backend:** FastAPI + SQLAlchemy 2 + Pydantic v2
- **DB:** PostgreSQL (local dev supported; Cloud SQL in hosted envs)
- **AI:** Pluggable `LegalAIService` (default = deterministic stub for local dev — swap to self-hosted LLM / Ollama / internal API for prod)
- **Auth:** Email + password + JWT + 5-role RBAC
- **Document storage:** GCS (`gs://legalos/msa/…`) for MSA uploads + OnlyOffice saves; local filesystem optional for Docker-only dev
- **Dev:** Docker Compose

## Prerequisites

- Local PostgreSQL **or** access to a Postgres instance.
- For the individual (non-Docker) flow: Python 3.12+ and Node 18+.

## Configuration

```bash
cp .env.example .env
```

Then edit `.env` and set `DATABASE_URL` to your Postgres connection, plus a strong `JWT_SECRET`. The `.env` is read from the project root regardless of where you launch the backend from.

On first boot the backend seeds five sample users + playbook clauses + regulatory updates (idempotent). The **schema is managed by Alembic** — see below.

## Database migrations (Alembic)

The database schema is owned by Alembic migrations in [`backend/alembic/`](backend/alembic/) — the app no longer auto-creates tables. The DB connection comes from `DATABASE_URL` (same as the app).

```bash
cd backend

# Apply all migrations (create/upgrade schema to the latest revision)
alembic upgrade head

# Inspect state
alembic current          # revision the DB is on
alembic history          # all revisions

# After changing SQLAlchemy models — generate a new migration, then review it
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

> The Docker image runs `alembic upgrade head` automatically on startup (in the Dockerfile `CMD`), so `docker compose up` always migrates before serving.
>
> For an existing database whose tables predate Alembic, baseline it once with `alembic stamp head` instead of `upgrade` (records the current schema as the baseline without re-running DDL).

## JioLegal templates & Vertex RAG

JioLegal and AI contract-review suggestions use **JFPSL legal templates** in two ways:

1. **Vertex AI RAG Engine** — live retrieval via `search_jfpsl_knowledge` (corpus ID in GCP Secret Manager `legalos_dev` / `legalos_uat` / `legalos_prod`).
2. **Distilled prompt standards** — [`backend/app/orchestrator/prompts/jfpsl_template_standards.md`](backend/app/orchestrator/prompts/jfpsl_template_standards.md), generated from local DOCX templates.

Place approved template DOCX files in `Templates/` and executed contracts (PDF/DOCX) in
`contracts/` at the repo root (both gitignored). GCS mirrors:

- Templates → `gs://legalos/legal_templates/`
- Executed → `gs://legalos/contracts/`

```bash
# Templates → Vertex RAG
docker cp Templates legalos-backend:/tmp/Templates
docker exec legalos-backend python /app/scripts/distill_template_playbook.py --templates-dir /tmp/Templates
docker exec legalos-backend python /app/scripts/sync_templates_to_rag.py --templates-dir /tmp/Templates

# Executed contracts → same Vertex RAG corpus
docker cp contracts legalos-backend:/tmp/contracts
docker exec legalos-backend python /app/scripts/sync_contracts_to_rag.py --contracts-dir /tmp/contracts

# Dry-run / force re-upload
docker exec legalos-backend python /app/scripts/sync_contracts_to_rag.py --contracts-dir /tmp/contracts --dry-run
docker exec legalos-backend python /app/scripts/sync_contracts_to_rag.py --contracts-dir /tmp/contracts --force
```

Upload state (gitignored): `backend/config/.rag_upload_state.json` (templates) and
`backend/config/.rag_contracts_upload_state.json` (executed).

**Retrieval order for LawGenie:** `search_jfpsl_knowledge` (templates + executed corpus) first →
`web_search` if no internal hits → answer with source labels.

## Run with Docker (whole app)

```bash
# Build and start backend + frontend (+ OnlyOffice) (backend runs migrations first)
docker compose up --build
```

- Frontend: <http://localhost:5173>
- Backend API + Swagger docs: <http://localhost:8000/docs>

> Note: Docker Compose does not bundle Postgres; set `DATABASE_URL` to your local Postgres (e.g. `127.0.0.1:5432`) or hosted DB.

## Run each service individually

**Backend** (FastAPI on :8000):

```bash
cd backend
# Use Python 3.12 (see backend/.python-version). If you only have 3.14 installed,
# install 3.12 first: brew install python@3.12
./scripts/setup-venv.sh
source .venv/bin/activate
alembic upgrade head                  # apply migrations first
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend** (Vite dev server on :5173):

```bash
cd frontend
npm install
npm run dev
```

The frontend reads the API base URL from `VITE_API_BASE_URL` (defaults to <http://localhost:8000>).

## Gmail integration

LegalOS connects to Gmail via OAuth 2.0 for Task Manager auto-ingest, MSA vendor threads, and (optionally) Legal Bot email context.

### Google Cloud setup

1. In your GCP project, enable **Gmail API**, **Google Drive API**, **Google Docs API**, and **Google Sheets API** (`APIs & Services → Library`).
2. Configure the **OAuth consent screen** and add scopes (mapped to LegalOS features):

   | Scope | Why LegalOS needs it |
   | ----- | -------------------- |
   | `https://www.googleapis.com/auth/gmail.readonly` | Read full messages, threads, attachments, labels (Task Manager poll, MSA vendor ingest, Legal Bot context) |
   | `https://www.googleapis.com/auth/gmail.send` | Send mail (`/messages/send` — MSA vendor send, AI draft send) |
   | `https://www.googleapis.com/auth/gmail.modify` | Label / message updates beyond send |
   | `https://www.googleapis.com/auth/gmail.metadata` | Header-only listing without body |
   | `https://www.googleapis.com/auth/drive.file` | Drive files the user opens/creates with LegalOS (not full Drive) |
   | `https://www.googleapis.com/auth/documents` | Native Google Docs API (Drive alone only reads blobs) |
   | `https://www.googleapis.com/auth/spreadsheets` | Native Google Sheets API |

3. Create an **OAuth 2.0 Client ID** (type: Web application).
4. Add **Authorized redirect URIs** for each environment:
   - Local: `http://localhost:8000/api/gmail/oauth/callback`
   - Dev: `https://legalos-dev.jiofinance.in/api/gmail/oauth/callback`
   - Prod: `https://legalos.jiofinance.in/api/gmail/oauth/callback`
5. Copy the client ID and secret into `.env` (see `.env.example`).

### Environment variables

| Variable | Purpose |
| -------- | ------- |
| `GMAIL_CLIENT_ID` | OAuth client ID from GCP |
| `GMAIL_CLIENT_SECRET` | OAuth client secret |
| `GMAIL_REDIRECT_URI` | Must match a registered redirect URI |
| `GMAIL_ENABLED` | Set `true` to run the background inbox poller |
| `GMAIL_POLL_INTERVAL_SECONDS` | Poll interval (default `120`) |
| `GMAIL_LABEL` | Default MSA label filter (default `LegalOS/MSA`) |

Users connect Gmail from **Task Manager** or **MSA Automation**, then choose which Gmail labels LegalOS may read (recommended: `LegalOS/Tasks`, `LegalOS/MSA`).

### Seeded login accounts

| Role          | Email                       | Password    |
| ------------- | --------------------------- | ----------- |
| Super Admin   | super.admin@jfpsl.in      | password123 |
| Legal Admin   | legal.admin@jfpsl.in      | password123 |
| Legal User    | legal.user@jfpsl.in       | password123 |
| Business User | business.user@jfpsl.in    | password123 |
| Read Only     | readonly@jfpsl.in         | password123 |

⚠ **Change all seeded passwords before any non-local deployment.**

## RBAC matrix

| Module            | Super Admin | Legal Admin | Legal User | Business User | Read Only |
| ----------------- | ----------- | ----------- | ---------- | ------------- | --------- |
| User mgmt / RBAC  | ✅          | ❌          | ❌         | ❌            | ❌        |
| Contract Review   | ✅          | ✅          | ✅         | ❌            | ❌        |
| Doc Comparison    | ✅          | ✅          | ✅         | ❌            | ❌        |
| LegalBot          | ✅          | ✅          | ✅         | ✅            | ❌        |
| Legal Research    | ✅          | ✅          | ✅         | ❌            | ❌        |
| MSA Automation    | ✅          | ✅          | ✅         | ❌            | ❌        |
| Legal News        | ✅          | ✅          | ✅         | ❌            | digest    |
| Playbook mgmt     | ✅          | ✅          | ❌         | ❌            | ❌        |
| Audit log         | ✅ all      | ✅ all      | own only   | own only      | ❌        |

Enforced at both the API (FastAPI dependency injection per route) and the UI (sidebar visibility + route guards).

## AI Service

LawGenie chat and structured jobs (MSA review, research notes, etc.) run through the
**ADK orchestrator** under `backend/app/orchestrator/` (`AI_BACKEND=adk`). There is no
separate chat `LegalAIService` facade.

A deterministic stub path remains available for local smoke tests when ADK is disabled:
`backend/app/services/ai_service.py` (`StubLegalAIService`) still covers older task-shaped
flows (keyword playbook review, difflib compare, KB bot, regulatory keyword notes).

**LawGenie modes:** Review / Research / Draft are composer modes on `POST /api/chat/sse`.
Research can enable parallel fan-out + citation verify via env flags (Dev/UAT first).
Structured UC-04 research notes remain at `POST /api/legal-research` — conversational
Research in LawGenie is a different product surface.

**Retrieval order for LawGenie:** regulatory corpus (the law) → JFPSL templates/executed →
web (mode-gated) → cite with Evidence.

## Audit log (BRD §7)

Every AI invocation and every user decision (Accept / Modify / Reject / Override / Send) writes an immutable row to `audit_logs` with: user_id, role, action_type, module, input_summary, ai_output_summary, confidence_score, human_decision, model_version, ip_address, session_id, timestamp. Retention target = 7 years per RBI.

## What's stubbed vs. real

| Area                       | This scaffold                          | Production target                                       |
| -------------------------- | -------------------------------------- | ------------------------------------------------------- |
| AI inference               | Deterministic stub                     | Self-hosted LLM (no external API calls for legal data)  |
| Vector DB                  | In-memory keyword search               | Weaviate / ChromaDB self-hosted                         |
| Document storage           | GCS (`DOCUMENT_STORAGE_BACKEND=gcs`, prefix `msa/`) or local (`LOCAL_STORAGE_PATH`) | — |
| Gmail integration (UC-05)  | OAuth + poller + send with attachments | Google Cloud project credentials in `.env`               |
| MSA versioning (UC-05)     | Full negotiation version chain         | `msa_document_versions`, auto-diff, LLM change summary  |
| Contract templates         | Central MSA/NDA library + per-deal upload | `/api/contract-templates`, `/contract-templates` UI   |
| File parsing (PDF/DOCX)    | `pypdf` + `python-docx` on upload      | Same pipeline for Gmail attachments                     |
| Regulatory scrapers (UC-06)| Manual ingest endpoint + seed data     | Scheduled scrapers for RBI / SEBI / IRDAI / etc.        |
| Auth                       | Email + password + JWT                 | SSO (Google OAuth / SAML) + MFA on admin roles          |

All of these are isolated behind interfaces — swap-in points are explicit in the code.

## Repo layout

```
backend/
  app/
    main.py              FastAPI entry, CORS, router registration, startup seed
    config.py            Pydantic settings (env-driven)
    database.py          SQLAlchemy engine + session
    core/
      security.py        Password hashing, JWT encode/decode
      rbac.py            Role → permission matrix
    models/              SQLAlchemy ORM models
    schemas/             Pydantic request/response schemas
    api/                 FastAPI routers (one per module + auth/users/audit)
    services/
      ai_service.py      LegalAIService interface + StubLegalAIService
      audit_service.py   Audit log writer
    init_data.py         First-boot seed (users, playbook, regulatory updates, KB)

frontend/
  src/
    main.tsx             React entry + router
    App.tsx              Route tree with RBAC guards
    lib/                 API client, auth helpers, utils
    components/          Layout, Sidebar, ProtectedRoute, UI primitives
    contexts/            AuthContext
    pages/               One page per module + Login/Dashboard/Audit/Users
```
