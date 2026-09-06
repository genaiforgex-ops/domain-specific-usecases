# ADR 001: Pluggable Adapters

## Context

GenAIForge Risk integrates with SSO, AI, OSINT, email, and object storage. Production services may not be available during Phase 0–1 development.

## Decision

All external integrations implement adapter protocols in `backend/app/adapters/`. Factory (`get_*_adapter()`) selects implementation via environment variables:

| Variable | Values | Default |
|----------|--------|---------|
| `AI_ADAPTER` | `mock` | `mock` |
| `SSO_ADAPTER` | `mock` | `mock` |
| `OSINT_ADAPTER` | `mock` | `mock` |
| `EMAIL_ADAPTER` | `mock` | `mock` |
| `STORAGE_ADAPTER` | `gcs` / `local` | `gcs` (deployed); `local` filesystem for dev |

## Consequences

- Swap to production adapters without changing domain services.
- Mock adapters provide deterministic demos and tests.
- M1 citations must reference `regulator_clauses.id` from DB, never free-text LLM output.
