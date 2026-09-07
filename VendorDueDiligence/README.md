# GenAIForge · Vendor Due Diligence

AI-assisted **third-party risk (TPRM)** — register vendors, screen them, decide with HITL, then monitor continuously with examiner-ready audit packs.

**Who it is for:** Risk, compliance, procurement, and outsourcing teams that must show continuous diligence — not annual checkbox reviews.

---

## What this demo shows

- Lifecycle: **Register → Screen → Decide → Monitor**
- Vendor registry with sticky context (demo vendor: **CloudNest**)
- Screening run → score, decision, conditions (including nth-party signals)
- Continuous **monitoring** alerts and questionnaire tracking
- **Inherent vs residual** risk with human acceptance of residual risk
- Controls mapped to frameworks (DORA / NIST / OCC / BIS)
- **Examiner audit pack** export and procurement / Pilot–Production packaging

Accent color: teal `#3D8B7A`. Theme toggle included.

---

## How to open

```bash
open VendorDueDiligence/index.html
```

Or:

```bash
cd VendorDueDiligence
python3 -m http.server 8080
# → http://localhost:8080
```

Requires network once for Google Fonts. No build step.

---

## Recommended walkthrough (≈2 minutes)

| Step | Panel | What to say / do |
| --- | --- | --- |
| 1 | **Dashboard** | Tell the lifecycle story. Point to KPIs and critical alerts. Open the **TPRM research pulse**, then jump to Procurement. |
| 2 | **Vendors** | Filter the registry and select **CloudNest** (context persists across panels). |
| 3 | **Due Diligence** | Run screening → review score, decision, and conditions → open Report. |
| 4 | **Report** | Red / green flags, tabs, PDF export, HITL sign-off. |
| 5 | **Monitoring** | Continuous alerts (certs, cyber, fourth-party, questionnaires). Click an alert to switch vendor context. |
| 6 | **Questionnaires** | Assignment status and fourth-party map; export forms pack. |
| 7 | **Risk scoring** | Inherent vs residual gauges; accept residual risk (HITL). |
| 8 | **Controls + Audit pack** | Map findings to frameworks; build examiner ZIP. |
| 9 | **Procurement** | TPRM checklist, Pilot / Production packages, trust strip. |
| 10 | **M1 Snapshot** | Outsourcing classification for the selected vendor. |

---

## What’s included

| File | Role |
| --- | --- |
| `index.html` | App shell and panels |
| `assets/styles.css` | Teal theme, light/dark |
| `assets/data.js` | Vendors, scores, monitoring, audit pack |
| `assets/app.js` | Navigation and interactions |
| `BUYER_NOTES.md` | TPRM research themes and sources |

---

## Product line

Maps to GenAIForge **Risk / Vendor Due Diligence**.

---

## Contact

[genaiforge.in](https://genaiforge.in) · contactus@genaiforge.in

*Demo / illustrative data — not a live screening or OSINT feed.*
