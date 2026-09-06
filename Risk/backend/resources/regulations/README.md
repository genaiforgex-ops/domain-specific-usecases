# Regulation source PDFs

Drop the gazetted source PDFs here, exact filenames so the ingestion
commands below match:

- `rbi_nbfc_outsourcing_2025.pdf` — RBI (NBFC – Managing Risks in Outsourcing) Directions, 2025
- `rbi_payments_bank_outsourcing_2025.pdf` — RBI (Payments Banks – Managing Risks in Outsourcing) Directions, 2025
- `sebi_ia_master_circular_2025.pdf` — SEBI Master Circular for Investment Advisers, 2025

After dropping a file, ingest it (run from `backend/`, with the venv active):

```sh
python -m app.scripts.regulation_ingest.load_clauses \
    --pdf resources/regulations/rbi_nbfc_outsourcing_2025.pdf \
    --regulator RBI --instrument NBFC \
    --source-doc "RBI (NBFC - Managing Risks in Outsourcing) Directions, 2025" \
    --ref-prefix RBI-NBFC-2025 --version v3

python -m app.scripts.regulation_ingest.load_clauses \
    --pdf resources/regulations/rbi_payments_bank_outsourcing_2025.pdf \
    --regulator RBI --instrument PAYMENTS_BANK \
    --source-doc "RBI (Payments Banks - Managing Risks in Outsourcing) Directions, 2025" \
    --ref-prefix RBI-PB-2025 --version v3

python -m app.scripts.regulation_ingest.load_clauses \
    --pdf resources/regulations/sebi_ia_master_circular_2025.pdf \
    --regulator SEBI --instrument IA \
    --source-doc "SEBI Master Circular for Investment Advisers, 2025" \
    --ref-prefix SEBI-MC-IA-2025 --version v3
```

Each run is idempotent (delete-then-insert by regulator+instrument+version)
and lands as clause_library_version `v3`, which `get_active_clause_version()`
picks up automatically (latest `effective_from` wins) — existing jobs
already pinned to `v1`/`v2` keep reading their original text.

See `app/scripts/regulation_ingest/` for how parsing works:
`extract_pdf.py` (PyMuPDF block extraction) → `chunk_clauses.py`
(paragraph-numbering + clause_ref) → `load_clauses.py` (DB upsert).
