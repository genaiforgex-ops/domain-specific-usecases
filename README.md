# domain-specific-usecases

Static, client-ready **GenAIForge** demos by industry vertical. Each folder is a self-contained HTML/CSS/JS pitch surface — open in a browser, no backend required (Google Fonts only).

Built for buyer conversations: ROI, HITL governance, audit trails, trust chips, and Pilot vs Production packaging.

---

## Quick start

```bash
# Campaign / creative governance
open Creatives/index.html

# Third-party risk / vendor DD
open VendorDueDiligence/index.html

# Contract / LegalOS workflow
open LegalWorkflow/index.html

# Other verticals
open Banking/index.html
open Healthcare/index.html
open Insurance/index.html
open Manufacturing/index.html
open RealEstate/index.html
open Retail/index.html
```

Or serve any folder locally:

```bash
cd Banking && python3 -m http.server 8080
# → http://localhost:8080
```

---

## Demos

| Folder | Product surface | Accent | What buyers see |
| --- | --- | --- | --- |
| **Creatives/** | Campaign Studio | Bronze `#B8956C` | Briefs → copy → design, brand guardrails, HITL approvals, ROI vs agency, **real 2025–26 marketing news pulse** |
| **VendorDueDiligence/** | Vendor DD / TPRM | Teal `#3D8B7A` | Register → screen → decide → monitor, questionnaires, inherent/residual risk, examiner audit pack, procurement checklist |
| **LegalWorkflow/** | LegalOS + **LegalBot** | Gold `#C4A035` | MSA automation, playbook-cited LegalBot, comparison, obligations, radar, trust center |
| **Banking/** | BFSI Voice Command Center | — | Advisory & collections voice agent, DPD playbooks, RBI/SEBI rails, PTP / hardship |
| **Healthcare/** | Healthcare vertical demo | — | Domain pitch surface for care / ops AI narratives |
| **Insurance/** | Insurance vertical demo | — | Claims / underwriting oriented client demo |
| **Manufacturing/** | Manufacturing vertical demo | — | Plant / ops AI use-case pitch |
| **RealEstate/** | Real estate vertical demo | — | Property / CX oriented demo |
| **Retail/** | Retail vertical demo | — | Commerce / retail AI pitch surface |

Flagship pitch paths for deep modules: **Creatives**, **VendorDueDiligence**, **LegalWorkflow** (each has `BUYER_NOTES.md` + a 2-minute README pitch).

---

## How to pitch (flagship three)

### Creatives — Campaign Studio
1. Open Home → role switch → numbered tour  
2. **ROI / Buy** — agency avoided, Pilot vs Production, trust  
3. Guardrails → Briefs → Copies → Design → Approvals  
4. Inbox / Performance — industry news with GenAIForge next actions  

### VendorDueDiligence — TPRM
1. Dashboard lifecycle rail → select **CloudNest**  
2. Due Diligence run → Report → Monitoring alerts  
3. Scoring (inherent/residual) → Controls → Audit pack ZIP  
4. Procurement checklist + packages  

### LegalWorkflow — LegalOS
1. Dashboard hero + CLM research pulse  
2. **LegalBot** — Review / Research / Draft with playbook § citations  
3. MSA timeline + negotiation memory → Playbooks  
4. Obligations + Trust center (SOC2/ISO demo-labeled, audit CSV)  

---

## Shared demo conventions

- **Brand:** GenAIForge (no legacy vendor branding)
- **Shell:** left nav, one panel at a time, sticky top bar, light/dark theme toggle
- **Trust:** demo-labeled SOC2/ISO chips where shown; inference-only / no public training callouts on buyer surfaces
- **HITL:** human gates on approvals, residual risk acceptance, and LegalBot counsel — not blind bulk AI
- **Offline:** works from `file://` except Google Fonts

---

## Repo layout

```
domain-specific-usecases/
├── README.md                 ← you are here
├── Creatives/                ← Campaign Studio (static)
├── VendorDueDiligence/       ← Vendor DD / TPRM (static)
├── LegalWorkflow/            ← LegalOS + LegalBot (static)
├── Banking/ Healthcare/ Insurance/
├── Manufacturing/ RealEstate/ Retail/
└── .gitignore
```

Each demo folder typically includes:

- `index.html` — shell + panels  
- `assets/styles.css` · `assets/app.js` · `assets/data.js`  
- `README.md` — open steps + pitch script  
- `BUYER_NOTES.md` — research themes (flagship demos)

---

## Notes

- Demo data is fictional unless a panel explicitly cites public industry sources (e.g. Creatives news pulse).  
- Do not commit secrets; `.env` files are gitignored.  
- Full-stack app trees previously used for local Docker (Marketing / Risk / Legal) were removed from this repo — client demos live in the static folders above.
