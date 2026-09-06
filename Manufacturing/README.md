# Manufacturing · Predictive Maintenance Showcase

Client-ready HTML demo for **GenAIForge** — plant floor schematic plus an AI predictive-maintenance copilot (as positioned in the GenAIForge industries deck).

## Open the demo

No build step. From this folder:

```bash
open index.html
```

Or serve locally:

```bash
cd Manufacturing
python3 -m http.server 8080
# then open http://localhost:8080
```

Requires network once for Google Fonts and Chart.js CDN.

## Theme

Default is **dark** (plant-ops console). Use the header toggle to switch to **light** mode — preference is saved in `localStorage` under `gf-theme`. Charts and the plant floor schematic update automatically.

## 2-minute walkthrough

1. **Plant floor schematic** (hero) — interactive SVG layout of lines/cells. Click a line to filter assets; click asset dots on the floor to inspect sensors.
2. Switch **Plant** (Pune / Chennai / Aurangabad) to show multi-site layouts.
3. **Compact KPIs** below the schematic — OEE, availability, critical alerts, predicted failures (7d).
4. **Charts & assets** — OEE/downtime trend, risk-ranked assets, sensor trends when an asset is selected.
5. **Floating AI stack** (bottom-right) — alert cards and AI insights. **Acknowledge** alerts or **Ask copilot** from a card.
6. **Expand chat** on the stack to open the full PM Copilot — try “Why is Line 3 degrading?” or “Draft a maintenance WO for A-301”.
7. **Approve WO** on a draft work order (human-in-the-loop guardrail).

## What’s included

| Area | Files |
|------|--------|
| Dashboard shell | `index.html` |
| Styles | `assets/styles.css` |
| Schematic, charts, floating copilot | `assets/app.js` |
| Mock plant / sensor / copilot scripts | `assets/data.js` |

All data is illustrative demo data — not live IoT.

## PPT mapping

- Predictive-maintenance copilots → floating recommendation stack + expand-to-chat + RUL / risk list  
- Production observability → plant floor schematic, KPIs, OEE/downtime charts  
- Guardrails → “recommendation only · human approve WO”

## Contact

- [genaiforge.in](https://genaiforge.in)  
- contactus@genaiforge.in
