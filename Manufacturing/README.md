# GenAIForge · Predictive Maintenance Showcase

Plant-ops demo for **predictive maintenance** — interactive floor schematic, OEE and downtime trends, risk-ranked assets, and an AI PM copilot that drafts work orders for human approval.

**Who it is for:** Plant managers, reliability engineers, and manufacturing digital leaders evaluating AI copilots on the shop floor.

---

## What this demo shows

- Interactive **plant floor schematic** (lines, cells, asset dots)
- Multi-site plants: Pune / Chennai / Aurangabad
- Compact KPIs: OEE, availability, critical alerts, predicted failures (7d)
- Charts: OEE / downtime trend and sensor series for selected assets
- Floating AI stack: alerts, insights, acknowledge, ask copilot
- Full **PM Copilot** chat with draft work orders
- HITL guardrail: **Approve WO** (recommendation only until human approves)

---

## How to open

```bash
open Manufacturing/index.html
```

Or:

```bash
cd Manufacturing
python3 -m http.server 8080
# → http://localhost:8080
```

Requires network once for Google Fonts and Chart.js CDN. No build step.

---

## Recommended walkthrough (≈2 minutes)

| Step | Focus | What to do |
| --- | --- | --- |
| 1 | **Plant schematic** | Click a line to filter assets; click asset dots to inspect sensors. |
| 2 | **Plant switcher** | Switch Pune / Chennai / Aurangabad. |
| 3 | **KPIs** | Call out OEE, availability, critical alerts, predicted failures. |
| 4 | **Charts & assets** | Show risk-ranked assets and sensor trends. |
| 5 | **Floating AI stack** | Acknowledge an alert or **Ask copilot** from a card. |
| 6 | **PM Copilot** | Expand chat — try “Why is Line 3 degrading?” or “Draft a maintenance WO for A-301”. |
| 7 | **Approve WO** | Emphasize human approval before work starts. |
| 8 | **Theme** | Toggle light/dark (`gf-theme`). |

---

## What’s included

| File | Role |
| --- | --- |
| `index.html` | Dashboard shell |
| `assets/styles.css` | Plant-ops light/dark theme |
| `assets/data.js` | Plants, sensors, copilot scripts |
| `assets/app.js` | Schematic, charts, floating copilot |

---

## Product line

Maps to GenAIForge **Manufacturing · Predictive Maintenance**.

---

## Contact

[genaiforge.in](https://genaiforge.in) · contactus@genaiforge.in

*Demo / illustrative data — not live IoT telemetry.*
