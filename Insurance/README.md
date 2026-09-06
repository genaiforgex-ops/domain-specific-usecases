# GenAIForge Insurance — Agentic Claims & FNOL

**Client showcase demo** · HTML + CSS + JS mock · no backend

Agentic claims processing & FNOL for insurers — multi-channel intake, extract/validate/assess, auto-settle or route adjuster. **Days → Mins**, **70% less manual**, **24/7**.

---

## Quick start

Open `index.html` in a browser (or serve locally):

```bash
cd Insurance
python3 -m http.server 8080
# → http://localhost:8080
```

No build step, no dependencies.

---

## Layout — Claim Journey Workspace

Unlike a traditional analytics dashboard, this demo uses a **claim journey workspace** focused on one claim at a time:

| Zone | Purpose |
|------|---------|
| **Stage rail** (top) | Horizontal pipeline: Intake → Extract → Validate → Assess → Settle/Route. Progress bar shows claim advancement. Click a stage to view stage-specific document content and filter the agent timeline. |
| **Claim picker** (left) | Slim list of claims — ID, type, channel, severity, current stage. Click to load. |
| **Paper pane** (centre-left) | Mock source documents styled as paper cards — content changes per stage (raw upload, OCR scan, policy match, damage assessment, settlement summary). |
| **Extract pane** (centre-right) | Stage-specific fields — intake metadata, OCR confidence bars, coverage checks, fraud signals, settlement line items. |
| **Agent timeline** (right) | Vertical multi-agent activity trail — not a chat drawer. Filters by selected stage. |
| **HITL bar** (bottom) | Human-in-the-loop: **Approve settle** or **Escalate to adjuster**. |

Selecting a claim shows a **stage-aware agent insight** banner at the top of the split view.

---

## Stage-specific document views

Each pipeline stage shows distinct mock extraction content in the paper and fields panes:

| Stage | Paper pane | Extract pane |
|-------|------------|--------------|
| **Intake** | Raw upload bundle · channel transcript · queued attachments | Intake metadata — channel, attachments, OCR pending |
| **Extract** | Source document with OCR scan overlay | Fields with animated confidence bars |
| **Validate** | Policy doc with match highlights | Policy match & coverage check results |
| **Assess** | Damage assessment summary | Estimate line items & fraud signal scan |
| **Settle / Route** | Settlement summary or adjuster packet | Settlement amounts, routing, audit trail |

Future stages (beyond the claim's current progress) are still explorable — the progress bar and claim list show actual pipeline position.

---

## Interactions

1. **Switch LOB** — Motor, Health, or Property claims load in the picker.
2. **Pick a claim** — Paper documents, extracted fields, timeline, insight, and HITL bar update. Stage rail jumps to the claim's current stage.
3. **Click stage rail** — Paper pane, extract pane, document tabs, insight banner, and timeline all update to that stage's content.
4. **Switch document tabs** — Stage-specific tabs (e.g. Intake bundle / Channel, Policy match / Coverage checks).
5. **Toggle theme** — Light/dark mode via header button. Preference stored in `localStorage` key `gf-theme`.
6. **Approve settle** — Enabled when AI recommends auto-settle. Shows toast + updates timeline.
7. **Escalate to adjuster** — Routes claim, updates timeline, disables buttons.

All data is static mock — actions update in-memory state only.

---

## Demo claims (Motor LOB)

| Claim | Type | Stage | AI recommendation |
|-------|------|-------|-------------------|
| CLM-2024-88421 | Rear-end collision | Assess | Auto-settle ₹38,250 |
| CLM-2024-88419 | Windshield crack | Settle | Already settled |
| CLM-2024-88415 | Theft — vehicle | Validate | Escalate (fraud 78) |
| CLM-2024-88412 | Side-swipe | Extract | Processing (OCR active) |
| CLM-2024-88408 | Multi-vehicle pile-up | Assess | Routed to adjuster |
| CLM-2024-88405 | Hit & run | Validate | Escalate |

Health and Property LOBs have 2 claims each.

---

## Visual design

### Dark mode (default)
- **Palette:** Slate `#0e141c` + teal `#2aa198` workspace
- Teal progress bar on stage rail, confidence bars on extract pane

### Light mode
- **Palette:** Warm `#f4f0e8` workspace with emphasised paper documents
- Paper cards use stronger shadows and `#fffdf8` stock
- Toggle via header button · persisted as `gf-theme` in `localStorage`

### Shared
- **Fonts:** Libre Franklin (UI) + Newsreader (document titles on paper cards)
- **Paper texture:** Warm cards with line rules, stage badges, and stamp overlays
- **Extract stage:** Animated confidence bars when OCR is in progress

---

## Files

```
Insurance/
├── index.html          # Claim journey workspace shell + theme bootstrap
├── README.md           # This file
└── assets/
    ├── data.js         # Mock claims, documents, timelines, stage hints
    ├── styles.css      # Light/dark themes, paper cards, stage rail, animations
    └── app.js          # Stage-aware panes, theme toggle, HITL actions
```

---

## Product positioning

**GenAIForge Insurance** demonstrates agentic claims orchestration:

- **Multi-channel FNOL** — WhatsApp, Voice IVR, Portal, Email normalised in < 90 seconds
- **Document intelligence** — Policy PDF, photos, FIR extracted with confidence scores per stage
- **Multi-agent pipeline** — Intake → Extract → Validate → Assess → Settle/Route with full audit trail
- **Human-in-the-loop** — AI recommends; adjuster approves settle or escalation
- **Outcomes** — Days → minutes first response, 70% less manual handling, 24/7 intake

[genaiforge.in](https://genaiforge.in) · contactus@genaiforge.in
