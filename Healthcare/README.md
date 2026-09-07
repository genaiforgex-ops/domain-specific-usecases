# GenAIForge · Patient Access Command Center

Clinic-facing demo for **24/7 patient access** — booking, no-show risk, protocol intake, and a Patient Assistant that **never diagnoses**. Clinicians stay in charge; AI books, reminds, and routes.

**Who it is for:** Hospital / clinic operations, patient access, and digital health teams that need assistive AI with hard clinical guardrails.

---

## What this demo shows

- Hero proofs: 24/7 access · fewer no-shows · **0 diagnoses by AI**
- Multi-clinic tabs (Mumbai / Bengaluru / Hyderabad)
- Risk calendar with low / mid / high badges and reminder status
- Protocol-guided intake that never outputs a diagnosis
- Patient Assistant (sidebar) for booking, reminders, and safe escalation
- Escalation queue with PII masked until claimed
- Light clinical / soft navy dark themes

---

## How to open

```bash
open Healthcare/index.html
```

Or:

```bash
cd Healthcare
python3 -m http.server 8080
# → http://localhost:8080
```

Requires network once for Google Fonts. No build step.

---

## Recommended walkthrough (≈90 seconds)

| Step | Focus | What to do |
| --- | --- | --- |
| 1 | **Hero proofs** | Call out 24/7 access, no-show reduction, and zero AI diagnoses. |
| 2 | **Clinic tabs** | Switch Mumbai / Bengaluru / Hyderabad. |
| 3 | **Risk calendar** | Click a high-risk slot → open intake (never a diagnosis). |
| 4 | **Patient Assistant** | Try: *Book a GP today* · *Send reminder for high-risk slot* · *Is this rash serious?* (guardrail + escalation). |
| 5 | **Protocols** | Show Respiratory / Pediatric fever / Appointment routing. |
| 6 | **Escalation queue** | PII masked until **Claim**. |
| 7 | **Theme** | Toggle light/dark (`gf-theme`). |

---

## What’s included

| File | Role |
| --- | --- |
| `index.html` | Command center shell |
| `assets/styles.css` | Clinical light/dark theme |
| `assets/data.js` | Clinics, slots, protocols, assistant scripts |
| `assets/app.js` | Calendar, assistant, escalation |

---

## Product line

Maps to GenAIForge **Patient Engagement & Triage** — assistive only, **not a medical device**.

---

## Contact

[genaiforge.in](https://genaiforge.in) · contactus@genaiforge.in

*Demo / illustrative data — not clinical decision support or a medical device.*
