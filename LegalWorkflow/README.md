# GenAIForge · LegalOS

Contract lifecycle workspace with **MSA automation**, playbook-governed **LegalBot**, post-signature **obligations**, and a buyer-facing **trust center**.

**Who it is for:** General counsel, legal ops, and CLM buyers who need AI that cites *their* playbook — with human review, not blind bulk edits.

---

## What this demo shows

- Dashboard pitch: HITL, citations, audit retention, obligations
- **LegalBot** — Review / Research / Draft modes with **playbook § citations**
- **MSA automation** — stage timeline, AI review note, negotiation memory
- **Playbooks** — standard vs deviation (escalate / reject / review)
- Document **comparison** with material-risk flags
- **Obligations** tracker and matters intake with SLAs
- **Trust center** — SOC2/ISO (demo-labeled), inference-only, audit CSV, Pilot / Production packages

Accent color: gold `#C4A035`. Theme toggle included.

---

## How to open

```bash
open LegalWorkflow/index.html
```

Or:

```bash
cd LegalWorkflow
python3 -m http.server 8080
# → http://localhost:8080
```

Requires network once for Google Fonts. No build step.

---

## Recommended walkthrough (≈2 minutes)

| Step | Panel | What to say / do |
| --- | --- | --- |
| 1 | **Dashboard** | Open the hero “why buy” story. Use tiles to deep-link. Show the **CLM research pulse**. |
| 2 | **LegalBot** | Switch Review / Research / Draft. Use a suggested prompt; show streaming answer + citation chip. |
| 3 | **MSA Automation** | Walk CloudNest stages, AI review with HITL note, negotiation memory (3-month cap rejection). Advance a stage. |
| 4 | **Playbooks** | Standard vs deviation table; jump back to LegalBot. |
| 5 | **Radar** | Regulatory items and buyer RFP themes → update playbook. |
| 6 | **Templates + Comparison** | Approved library; NovaPay hunk navigator with material flags. |
| 7 | **Obligations + Matters** | Post-signature tracker (SOC2, renewals); intake queue with SLAs. |
| 8 | **Trust center** | Trust chips, AI audit sample, CSV export, Pilot / Production packages. |
| 9 | **Tasks** | Priority filters; claim and complete. |

---

## What’s included

| File | Role |
| --- | --- |
| `index.html` | App shell and panels |
| `assets/styles.css` | Gold theme, LegalBot chat UI, light/dark |
| `assets/data.js` | MSAs, playbooks, LegalBot prompts, trust pack |
| `assets/app.js` | Navigation, LegalBot streaming, interactions |
| `BUYER_NOTES.md` | CLM / legal AI research themes and sources |

---

## Product line

Maps to GenAIForge **Legal / LegalOS**.

---

## Contact

[genaiforge.in](https://genaiforge.in) · contactus@genaiforge.in

*Demo / illustrative data — not live contract storage or legal advice.*
