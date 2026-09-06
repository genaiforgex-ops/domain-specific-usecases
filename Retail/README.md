# GenAIForge · Retail Conversational Commerce

Retail demo for **catalog-grounded shopping and support** — co-browse the merch wall, track orders visually, start returns, and hand off to a stylist with full chat context.

**Who it is for:** Retail CX, e-commerce, and contact-center leaders evaluating conversational commerce that stays tied to real catalog and order data.

---

## What this demo shows

- Editorial hero with 24/7 · conversion assist · tickets deflected proofs
- Honest merch wall: Fashion / Home / Electronics with matching product photography
- **Co-browse** — assistant filters the wall live while chat stays open
- **WISMO** order tracking rail (Placed → Delivered)
- Returns flow and VIP stylist handoff
- Agent ops view: tickets deflected, conversion %, handoffs, intent mix
- Light / dark theme

---

## How to open

```bash
open Retail/index.html
```

Or:

```bash
cd Retail
python3 -m http.server 8080
# → http://localhost:8080
```

Requires network for fonts and Unsplash product photos. No build step.

---

## Recommended walkthrough (≈90 seconds)

| Time | Focus | What to do |
| --- | --- | --- |
| 0:00 | **Hero** | Show lookbook / room photo and proof line. |
| 0:10 | **Catalog** | Switch Fashion / Home / Electronics — every card is a matching product photo. |
| 0:25 | **Co-browse** | Ask: *Show me something under ₹2,000* — wall filters live; matches stay highlighted. |
| 0:45 | **WISMO** | Ask: *Where is my order SF-284719?* — walk the tracking rail. Also try `SF-192847`, `NH-551023`, `NH-338901`, `TM-774512`, `TM-663401`. |
| 1:00 | **Return + stylist** | *Start a return* → policy + label toast. *I need a stylist* → VIP handoff with context. |
| 1:15 | **Agent view** | Header toggle for deflection, conversion, handoffs, intent mix. |
| 1:25 | **Theme / chat** | Toggle theme; close chat via ✕ / Esc / backdrop. |

---

## What’s included

| File | Role |
| --- | --- |
| `index.html` | Hero, merch wall, WISMO rail, side chat |
| `assets/styles.css` | Light/dark retail theme |
| `assets/data.js` | Products, orders, ops metrics |
| `assets/app.js` | Co-browse filter, WISMO, handoff |

---

## Product line

Maps to GenAIForge **Retail · Conversational Commerce**.

---

## Contact

[genaiforge.in](https://genaiforge.in) · contactus@genaiforge.in

*Demo data only — not a live catalog or OMS.*
