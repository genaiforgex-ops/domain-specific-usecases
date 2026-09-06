# GenAIForge · Domain-specific use cases

Client-ready **static demos** for GenAIForge industry verticals. Each folder is a self-contained HTML/CSS/JS experience — open it in a browser, no backend or build step required.

Use these for buyer meetings, RFPs, and internal walkthroughs. Flagship modules emphasize **ROI**, **human-in-the-loop (HITL) governance**, **auditability**, and **Pilot vs Production** packaging.

---

## Prerequisites

- A modern browser (Chrome, Edge, Safari, Firefox)
- Network once for **Google Fonts** (and Unsplash / Chart.js where noted)
- Optional: Python 3 if you prefer a local HTTP server instead of `file://`

---

## Quick start

From the repository root:

```bash
open Creatives/index.html
open VendorDueDiligence/index.html
open LegalWorkflow/index.html
open Banking/index.html
open Healthcare/index.html
open Insurance/index.html
open Manufacturing/index.html
open RealEstate/index.html
open Retail/index.html
```

Or serve any folder:

```bash
cd Banking
python3 -m http.server 8080
# → http://localhost:8080
```

---

## Demo catalog

| Folder | Product | Audience | What you will see |
| --- | --- | --- | --- |
| [**Creatives/**](Creatives/) | Campaign Studio | Marketing / brand / agencies | Brief → copy → design, brand guardrails, HITL approvals, ROI, real marketing news pulse |
| [**VendorDueDiligence/**](VendorDueDiligence/) | Vendor DD / TPRM | Risk / procurement / compliance | Register → screen → decide → monitor, scoring, audit pack, procurement checklist |
| [**LegalWorkflow/**](LegalWorkflow/) | LegalOS + LegalBot | Legal / CLM / GC office | MSA automation, playbook-cited LegalBot, obligations, trust center |
| [**Banking/**](Banking/) | BFSI Voice Command Center | BFSI collections / advisory | Live call floor, DPD playbooks, customer 360, RBI/SEBI compliance rails |
| [**Healthcare/**](Healthcare/) | Patient Access Command Center | Clinics / patient access | 24/7 booking, no-show risk, protocol intake, non-diagnostic assistant |
| [**Insurance/**](Insurance/) | Agentic Claims & FNOL | Insurers / claims ops | Multi-stage claim journey, extract/validate/assess, HITL settle or escalate |
| [**Manufacturing/**](Manufacturing/) | Predictive Maintenance | Plant ops / reliability | Plant schematic, OEE, risk-ranked assets, PM copilot with WO approval |
| [**RealEstate/**](RealEstate/) | Sales Command Center | Developers / sales | Lead qualify, site-plan heat, unit match, visit booking |
| [**Retail/**](Retail/) | Conversational Commerce | Retail / CX | Co-browse catalog, order tracking (WISMO), returns, stylist handoff |

**Deepest pitch modules:** Creatives, VendorDueDiligence, LegalWorkflow — each includes `BUYER_NOTES.md` with research themes and sources.

---

## Shared conventions

| Convention | Detail |
| --- | --- |
| Brand | GenAIForge |
| UI pattern | Sidebar (or journey workspace), one focus surface, theme toggle |
| Trust | SOC2 / ISO chips are **demo-labeled** where shown; inference-only / no public training callouts on buyer surfaces |
| HITL | Humans approve — creatives, residual risk, settlements, work orders, LegalBot counsel |
| Data | Illustrative demo data unless a panel cites public industry sources |

---

## Repository layout

```
domain-specific-usecases/
├── README.md
├── Creatives/              # Campaign Studio
├── VendorDueDiligence/     # Third-party risk
├── LegalWorkflow/          # LegalOS + LegalBot
├── Banking/
├── Healthcare/
├── Insurance/
├── Manufacturing/
├── RealEstate/
├── Retail/
└── .gitignore
```

Typical demo folder contents:

| File | Purpose |
| --- | --- |
| `index.html` | Application shell |
| `assets/styles.css` | Theme and layout |
| `assets/data.js` | Demo datasets |
| `assets/app.js` | Interactions |
| `README.md` | How to open + pitch guide |
| `BUYER_NOTES.md` | Research notes (flagship demos) |

---

## Contact

- Website: [genaiforge.in](https://genaiforge.in)
- Email: contactus@genaiforge.in

---

## Notes

- Do not commit secrets; `.env` files are gitignored.
- These demos are for presentation only — not production systems, live telephony, LMS, OMS, or medical devices.
