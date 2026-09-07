# GenAIForge · Agentic Claims & FNOL

Insurer demo for **agentic claims processing** — multi-channel FNOL intake, extract / validate / assess, then auto-settle or route to an adjuster with human-in-the-loop control.

**Who it is for:** Claims leaders, FNOL / ops, and digital insurance teams evaluating AI that shortens cycle time without removing adjuster oversight.

---

## What this demo shows

- Claim journey workspace (one claim at a time — not a metrics dashboard)
- Stage rail: **Intake → Extract → Validate → Assess → Settle / Route**
- Stage-aware paper documents, field extraction, and agent timeline
- Lines of business: Motor, Health, Property
- HITL bar: **Approve settle** or **Escalate to adjuster**
- Outcomes narrative: days → minutes, less manual handling, 24/7 intake

---

## How to open

```bash
open Insurance/index.html
```

Or:

```bash
cd Insurance
python3 -m http.server 8080
# → http://localhost:8080
```

No build step. No backend dependencies.

---

## Workspace layout

| Zone | Purpose |
| --- | --- |
| **Stage rail** (top) | Pipeline progress; click a stage to filter documents and timeline |
| **Claim picker** (left) | Claims list — ID, type, channel, severity, stage |
| **Paper pane** | Mock source documents per stage |
| **Extract pane** | Fields, confidence bars, coverage / fraud / settlement lines |
| **Agent timeline** (right) | Multi-agent activity trail (not a chat drawer) |
| **HITL bar** (bottom) | Approve settle or escalate |

---

## Recommended walkthrough

1. **Switch LOB** — Motor, Health, or Property.
2. **Pick a claim** — paper, fields, timeline, and HITL update to that claim’s stage.
3. **Click the stage rail** — explore stage-specific documents even beyond current progress.
4. **Approve settle** or **Escalate** — toast + timeline update (in-memory only).
5. **Toggle theme** — light/dark (`gf-theme`).

### Sample Motor claims

| Claim | Type | Stage | AI recommendation |
| --- | --- | --- | --- |
| CLM-2024-88421 | Rear-end collision | Assess | Auto-settle ₹38,250 |
| CLM-2024-88419 | Windshield crack | Settle | Already settled |
| CLM-2024-88415 | Theft — vehicle | Validate | Escalate (fraud signal) |
| CLM-2024-88412 | Side-swipe | Extract | OCR in progress |
| CLM-2024-88408 | Multi-vehicle | Assess | Routed to adjuster |
| CLM-2024-88405 | Hit & run | Validate | Escalate |

Health and Property each include additional sample claims.

---

## What’s included

| File | Role |
| --- | --- |
| `index.html` | Claim journey shell |
| `assets/styles.css` | Light/dark, paper cards, stage rail |
| `assets/data.js` | Claims, documents, timelines |
| `assets/app.js` | Stage panes, theme, HITL actions |

---

## Product line

Maps to GenAIForge **Insurance · Agentic Claims & FNOL**.

---

## Contact

[genaiforge.in](https://genaiforge.in) · contactus@genaiforge.in

*Demo / illustrative data — not a live claims system.*
