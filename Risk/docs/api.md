# GenAIForge Risk API

Base URL: `http://localhost:8000/api/v1`

Interactive docs: `http://localhost:8000/docs`

## Authentication

Email/password via `POST /auth/login`. Session is an httpOnly cookie (`genaiforge_session`).
Use the interactive docs cookie jar, or send `Authorization: Bearer <token>` from the login response.

## Modules

### M1 — Classification

| Method | Path | Description |
|--------|------|-------------|
| GET | `/classifications` | List jobs |
| POST | `/classifications` | Create job (async classify) |
| POST | `/classifications/upload` | Upload file + classify |
| GET | `/classifications/{id}` | Get job |
| POST | `/classifications/{id}/confirm` | Confirm AI label |
| POST | `/classifications/{id}/override` | Override (min 20 char justification) |
| GET | `/vendors/{id}/classification` | Latest confirmed classification |

### M2 — Vendor DD

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/vendors` | List / create |
| POST | `/vendors/{id}/dd-runs` | Run due diligence |
| GET | `/dd-reports/{id}` | Get report with findings |
| POST | `/dd-reports/{id}/sign-off` | Manager sign-off |
| GET | `/dd-reports/{id}/export.pdf` | PDF export |

### M3 — Scoring

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/projects` | List / create |
| POST | `/projects/{id}/score` | Compute deterministic scores |
| POST | `/projects/{id}/what-if` | Projected residual |
| POST | `/risk-scores/{id}/override` | Override with justification |

### Cross-cutting

| Method | Path | Description |
|--------|------|-------------|
| GET | `/audit` | Audit log |
| GET | `/search?q=` | Unified search |
| GET | `/dashboards/operational` | Queue KPIs |
| GET | `/dashboards/risk-trends` | Score trends |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| PATCH | `/admin/ai-config/{module}` | Kill-switch / thresholds |
| GET/PUT | `/admin/dd-weights` | Red-flag weights |
