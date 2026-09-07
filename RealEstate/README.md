# GenAIForge · Real Estate Sales Command Center

Sales demo for **24/7 lead qualification**, site-visit booking, and matching the right buyer to the right unit — with live voice qualify and site-plan heat.

**Who it is for:** Developer sales heads, CRM / digital sales, and channel partners evaluating voice + matching AI for project inventory.

---

## What this demo shows

- Full-bleed project photography with speed and live-voice proof
- City switcher: Pune / Mumbai / Bangalore
- **Site-plan heat** — towers sized by buyer interest; visit-today rings
- Match intelligence: interested buyers + suggested inventory with match %
- Live qualify conversation (greet → budget → book visit)
- Today’s visits with reminder status and Lead Qualifier side panel
- Light / dark theme for projector or daytime meetings

---

## How to open

```bash
open RealEstate/index.html
```

Or:

```bash
cd RealEstate
python3 -m http.server 8080
# → http://localhost:8080
```

Requires network for fonts and Unsplash project / unit photos. No build step.

---

## Recommended walkthrough (≈90 seconds)

| Time | Focus | What to do |
| --- | --- | --- |
| 0:00 | **Hero** | Show project photo, &lt;60s speed chip, live voice badge, proof line. |
| 0:15 | **City tabs** | Switch Pune / Mumbai / Bangalore — hero, site plan, and matches update. |
| 0:25 | **Site-plan heat** | Click the hottest tower; explain interest-by-unit-type. |
| 0:40 | **Match strip** | Walk interested buyers and suggested inventory → **Assign visit**. |
| 0:55 | **Live qualify** | **Watch live qualify** → advance greet → budget → book visit. |
| 1:15 | **Today’s visits** | Open a visit card → Lead Qualifier side bar. |
| 1:25 | **Theme** | Toggle light/dark (`gf-theme`). |

---

## What’s included

| File | Role |
| --- | --- |
| `index.html` | Photo hero, site plan, match, live call, visits |
| `assets/styles.css` | Luxury dark/light theme |
| `assets/data.js` | Projects, photos, clusters, inventory, scripts |
| `assets/app.js` | Rendering and interactions |

---

## Product line

Maps to GenAIForge **Real Estate · Sales & Lead Qualification**.

---

## Contact

[genaiforge.in](https://genaiforge.in) · contactus@genaiforge.in

*Demo data only — not a live CRM or telephony system.*
