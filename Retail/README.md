# GenAIForge · Retail Conversational Commerce

Client demo for **catalog-grounded shopping + support**: co-browse the merch wall, track orders visually, start returns, hand off to a stylist.

---

## Open

```bash
open /Users/vikasmaurya/Downloads/UseCases/Retail/index.html
```

Or:

```bash
cd Retail && python3 -m http.server 8080
```

Needs network for fonts + Unsplash product photos.

---

## 90-second client pitch

### 0:00 — Editorial hero
Real lookbook / room / tech-desk photo. Proof line: **24/7 · conversion assist · tickets deflected**.

### 0:10 — The catalog is honest
Every card is a **matching product photo** (linen shirt, sofa, headphones — not random placeholders). Switch **Fashion / Home / Electronics**.

### 0:25 — Co-browse
**Ask assistant** (or the coral bubble). Try **“Show me something under ₹2,000”** — the wall **filters live** while the side chat stays open. Cards dim; matches stay highlighted.

### 0:45 — WISMO
**“Where is my order SF-284719?”** — tracking rail: Placed → Packed → In transit → Out for delivery → Delivered.

Also: `SF-192847`, `NH-551023`, `NH-338901`, `TM-774512`, `TM-663401`.

### 1:00 — Return + stylist
**“Start a return”** → policy + label toast.  
**“I need a stylist”** → VIP handoff with chat context.

### 1:15 — Agent view
Header toggle: tickets deflected, conversion %, handoffs, intent mix.

### 1:25 — Theme
Sun/moon · `gf-theme` · light stone default · dark merch wall · **no cream/terracotta**. Chat closes via **✕ / Esc / backdrop**.

---

## Files

| File | Role |
|------|------|
| `index.html` | Hero, merch wall, WISMO rail, side chat |
| `assets/styles.css` | Fraunces + Plus Jakarta Sans · light/dark |
| `assets/data.js` | Correct Unsplash SKUs, orders, ops |
| `assets/app.js` | Co-browse filter, WISMO, handoff |

---

## Contact

[genaiforge.in](https://genaiforge.in) · contactus@genaiforge.in

*Demo data only — not a live catalog or OMS.*
