# Regulatory document staging

Drop official PDFs here for bulk ingestion, named after their manifest `doc_id`
from `backend/config/REGULATORY_CORPUS_MANIFEST.csv`:

```
backend/regulatory_corpus/
  LEND-DLD-2025.pdf
  AML-MD-KYC.pdf
  DP-DPDPA-2023 - dpdp act.pdf     # a doc_id prefix works too
```

Then:

```bash
docker exec legalos-backend python scripts/sync_regulatory_to_rag.py --list   # what's expected
docker exec legalos-backend python scripts/sync_regulatory_to_rag.py          # ingest
```

Only download from the regulator's own site (`official_url` in the manifest) —
`rbi.org.in`, `sebi.gov.in`, `irdai.gov.in`, `npci.org.in`, `meity.gov.in`,
`indiacode.nic.in`. Copyrighted commentary (Taxmann, EBC) must not go into the
corpus: the bot would paraphrase someone's opinion instead of citing the rule.

Single documents can also be uploaded from the **Regulatory Corpus** admin page,
which shows per-document status and lets you inspect the extracted clauses.

The documents themselves are not committed — only this README.
