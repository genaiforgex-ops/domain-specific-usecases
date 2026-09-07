/* GenAIForge Creatives — Campaign Studio panel shell */
(function () {
  "use strict";

  const D = () => window.CREATIVES_DATA;
  const TITLES = {
    home: ["Home", "Buyer pitch · numbered tour · role focus"],
    briefs: ["Briefs", "List · detail · stage rail · comments"],
    copies: ["Copies", "Waiting/done · AI vs edited · versions"],
    design: ["Design", "Creatives → Template → Heroes → Export"],
    calendar: ["Calendar", "Launch plan · channels · readiness"],
    assets: ["Assets", "Approved library · reuse"],
    guardrails: ["Guardrails", "Tone · banned claims · prompt studio"],
    performance: ["Performance", "CTR + industry context → next brief"],
    inbox: ["Inbox", "Mentions · real industry news pulse"],
    approvals: ["Approvals", "Gates · SLA · checklist · decisions"],
    activity: ["Activity", "Actor timeline with event types"],
    roi: ["ROI / Buy", "Business case · trust · Pilot / Production"],
  };
  const DESIGN_STEPS = ["Creatives", "Template", "Heroes", "Export"];
  const GATE_LABELS = {
    brief_review: "Brief review",
    creative_review: "Creative review",
    final_signoff: "Final sign-off",
  };

  const state = {
    roleId: "PL",
    briefId: "b1",
    panel: "home",
    queueTab: "waiting",
    designStep: 0,
    selectedBanner: null,
    selectedTemplate: "Performance hero",
    selectedAsset: "a1",
    pitchIdx: 0,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function toast(msg) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove("show"), 2800);
  }

  function role() {
    return D().roles.find((r) => r.id === state.roleId);
  }

  function brief() {
    return D().briefs.find((b) => b.id === state.briefId);
  }

  function stageIndex(id) {
    return D().stages.findIndex((s) => s.id === id);
  }

  function isLight() {
    return document.documentElement.classList.contains("gf-theme-light");
  }

  function applyTheme(mode) {
    document.documentElement.classList.remove("gf-theme-light", "gf-theme-dark");
    document.documentElement.classList.add(mode === "light" ? "gf-theme-light" : "gf-theme-dark");
    localStorage.setItem("gf-theme", mode === "light" ? "light" : "dark");
    const meta = $("themeColorMeta");
    if (meta) meta.content = mode === "light" ? "#f6f7f9" : "#0B0C10";
  }

  function statusChip(status) {
    const map = {
      draft: "chip-muted",
      submitted: "chip-warn",
      in_progress: "chip",
      in_review: "chip-warn",
      approved: "chip-ok",
    };
    return map[status] || "chip";
  }

  function pushActivity(b, type, text) {
    b.activity.unshift({
      at: "Just now",
      actor: role().name,
      initials: role().name
        .split(" ")
        .map((p) => p[0])
        .join("")
        .slice(0, 2),
      type: type,
      text: text,
    });
  }

  function updateNavBadges() {
    const awaiting = role().kpis.await;
    $("navBriefs").textContent = String(D().briefs.filter((b) => b.status !== "approved").length);
    $("navCopies").textContent = String((D().queues[state.roleId].waiting || []).length);
    let pendingGates = 0;
    D().briefs.forEach((b) => {
      Object.values(b.gates).forEach((g) => {
        if (g.status === "pending") pendingGates += 1;
      });
    });
    $("navApprovals").textContent = String(pendingGates || awaiting);
    const inboxEl = $("navInbox");
    if (inboxEl) inboxEl.textContent = String(D().inbox.filter((i) => i.status !== "closed").length + D().industryNews.length);
  }

  function renderPitchStrip() {
    const steps = D().pitchSteps;
    const step = steps[Math.min(state.pitchIdx, steps.length - 1)];
    const next = steps[Math.min(state.pitchIdx + 1, steps.length - 1)];
    $("pitchStrip").innerHTML =
      `<strong>Client pitch</strong>` +
      `<span>Step ${state.pitchIdx + 1}/${steps.length}: ${step.label} — ${step.detail}</span>` +
      `<button type="button" class="btn btn-accent btn-sm" id="pitchNextBtn">${
        state.pitchIdx >= steps.length - 1 ? "Replay from Briefs" : "Next: " + next.label
      }</button>`;
    $("pitchNextBtn").addEventListener("click", () => {
      if (state.pitchIdx >= steps.length - 1) state.pitchIdx = 0;
      else state.pitchIdx += 1;
      const target = D().pitchSteps[state.pitchIdx];
      showPanel(target.panel);
    });
  }

  function showPanel(id) {
    state.panel = id;
    const pitchMatch = D().pitchSteps.findIndex((p) => p.panel === id);
    if (pitchMatch >= 0) state.pitchIdx = pitchMatch;
    document.querySelectorAll(".nav-item").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-panel") === id);
    });
    document.querySelectorAll("[data-view]").forEach((v) => {
      v.hidden = v.id !== "view-" + id;
    });
    const t = TITLES[id] || [id, ""];
    $("pageTitle").textContent = t[0];
    $("pageSub").textContent = t[1];
    renderPitchStrip();
    renderPanel();
  }

  function renderHome() {
    const r = role();
    const initials = r.name
      .split(" ")
      .map((p) => p[0])
      .join("")
      .slice(0, 2);

    $("heroPitch").innerHTML = `<div class="hero-inner">
      <p class="hero-eyebrow">GenAIForge · Campaign Studio</p>
      <h2>Governed creative production buyers can defend</h2>
      <p>Brand + disclosure guardrails in the loop · HITL SLAs · real industry news wired into briefs — ROI CFOs recognize, not just “hours saved.”</p>
      <div class="hero-proof">
        <div><strong>62%</strong><span>Agency spend avoided</span></div>
        <div><strong>4.2d</strong><span>Brief → sign-off</span></div>
        <div><strong>100%</strong><span>Pre-publish brand checks</span></div>
      </div>
      <div class="row-actions" style="padding:0;margin-top:0.85rem">
        <button type="button" class="btn btn-accent" data-goto="roi">Open buyer ROI</button>
        <button type="button" class="btn btn-ghost" data-goto="inbox">Industry news pulse</button>
        <button type="button" class="btn btn-ghost" id="startTourBtn">Start numbered tour</button>
      </div>
    </div>`;
    $("heroPitch").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });
    $("startTourBtn").addEventListener("click", () => {
      state.pitchIdx = 0;
      showPanel(D().tour[0].panel);
      toast("Tour step 1 · " + D().tour[0].title);
    });

    $("personaCard").innerHTML = `<div class="persona">
      <div class="persona-av">${initials}</div>
      <div>
        <h3>${r.name}</h3>
        <div class="role">${r.title} · Campaign Studio</div>
        <div class="focus"><strong>Focus:</strong> ${r.focus}</div>
      </div>
    </div>`;

    const max = Math.max.apply(null, r.activity14.concat([1]));
    $("sparkWrap").innerHTML =
      `<div class="spark-bars">${r.activity14
        .map((n) => `<span style="height:${Math.round((n / max) * 100)}%"></span>`)
        .join("")}</div>` +
      `<div class="spark-meta"><span>14 days ago</span><span>Today · ${r.activity14[r.activity14.length - 1]} events</span></div>`;

    $("kpiRow").innerHTML = [
      [r.kpis.await, "Awaiting you"],
      [r.kpis.review, "In review"],
      [r.kpis.shipped, "Shipped (14d)"],
    ]
      .map(([n, l]) => `<div class="kpi"><strong>${n}</strong><span>${l}</span></div>`)
      .join("");

    $("tourGrid").innerHTML = D()
      .tour.map(
        (t) => `<button type="button" class="tour-card" data-goto="${t.panel}">
        <span class="tour-n">${t.n}</span>
        <div class="fc-title">${t.title}</div>
        <div class="fc-sub">${t.blurb}</div>
      </button>`
      )
      .join("");
    $("tourGrid").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });

    $("stageCounts").innerHTML = D()
      .stages.map((s) => {
        const n = D().briefs.filter((b) => b.stage === s.id).length;
        return `<div class="stage-count"><strong>${n}</strong><span>${s.label}</span></div>`;
      })
      .join("");

    const focus = [
      { panel: "briefs", label: "Briefs", title: brief().name, sub: "Open detail · advance pipeline" },
      { panel: "calendar", label: "Calendar", title: "Launch readiness", sub: "Channels · asset status" },
      { panel: "inbox", label: "Inbox", title: "Mentions + news", sub: "Real headlines · SLA breaches" },
      { panel: "roi", label: "ROI", title: "Buyer business case", sub: "Pilot vs Production" },
    ];
    $("focusCards").innerHTML = focus
      .map(
        (f) => `<button type="button" class="focus-card" data-goto="${f.panel}">
        <div class="fc-label">${f.label}</div>
        <div class="fc-title">${f.title}</div>
        <div class="fc-sub">${f.sub}</div>
      </button>`
      )
      .join("");
    $("focusCards").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });

    $("newsFeed").innerHTML = D()
      .industryNews.slice(0, 5)
      .map(
        (n) => `<article class="news-card">
        <div class="news-meta"><span class="chip chip-muted">${n.source}</span><span class="page-sub">${n.date}</span></div>
        <div class="fc-title">${n.title}</div>
        <p class="news-take">${n.takeaway}</p>
        <p class="news-act"><strong>GenAIForge:</strong> ${n.forgeAction}</p>
        <div class="row-actions" style="padding:0;margin-top:0.45rem">
          ${
            n.briefHint
              ? `<button type="button" class="btn btn-sm btn-accent" data-brief="${n.briefHint}">Open related brief</button>`
              : `<button type="button" class="btn btn-sm btn-ghost" data-goto="guardrails">Open guardrails</button>`
          }
          <button type="button" class="btn btn-sm btn-ghost" data-goto="inbox">Full pulse</button>
        </div>
        <p class="news-cite">Demo / illustrative citation · public reporting</p>
      </article>`
      )
      .join("");
    $("newsFeed").querySelectorAll("[data-brief]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.briefId = btn.getAttribute("data-brief");
        showPanel("briefs");
        toast("Opened brief inspired by industry news");
      });
    });
    $("newsFeed").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });
  }

  function renderCalendar() {
    $("calBoard").innerHTML = `<div class="cal-table">
      <div class="cal-head"><span>Campaign</span><span>Channel</span><span>Date</span><span>Assets</span><span>Status</span></div>
      ${D()
        .calendar.map(
          (c) => `<button type="button" class="cal-row" data-brief="${c.briefId}">
          <span>${c.campaign}</span><span>${c.channel}</span><span>${c.date}</span>
          <span>${c.assets}</span><span class="chip chip-muted">${c.status.replace(/_/g, " ")}</span>
        </button>`
        )
        .join("")}
    </div>`;
    $("calBoard").querySelectorAll(".cal-row").forEach((row) => {
      row.addEventListener("click", () => {
        state.briefId = row.getAttribute("data-brief");
        showPanel("briefs");
        toast("Opened brief from calendar");
      });
    });
  }

  function renderGuardrails() {
    const g = D().guardrails;
    $("guardLeft").innerHTML = `<div class="pad">
      <h2 style="margin:0 0 0.5rem;font-family:var(--font-display);font-size:1.05rem">Brand tone</h2>
      <ul class="bullet-list">${g.tone.map((t) => `<li>${t}</li>`).join("")}</ul>
      <h2 style="margin:1rem 0 0.5rem;font-family:var(--font-display);font-size:1.05rem">Banned claims</h2>
      <div class="chip-row">${g.banned.map((b) => `<span class="chip chip-danger">${b}</span>`).join("")}</div>
      <h2 style="margin:1rem 0 0.5rem;font-family:var(--font-display);font-size:1.05rem">Logo lockups</h2>
      ${g.logo
        .map(
          (l) => `<div class="rule-row"><span>${l.rule}</span><span class="chip ${l.status === "enforced" ? "chip-ok" : "chip-warn"}">${l.status}</span></div>`
        )
        .join("")}
    </div>`;
    $("guardRight").innerHTML = `<div class="pad">
      <h2 style="margin:0 0 0.35rem;font-family:var(--font-display);font-size:1.05rem">Prompt studio</h2>
      <p class="page-sub" style="margin:0 0 0.75rem">Pre-generation compliance score (demo)</p>
      ${g.prompts
        .map(
          (p) => `<article class="prompt-card">
          <div class="prompt-top"><strong>${p.name}</strong><span class="chip">${p.score}% safe</span></div>
          <p>${p.body}</p>
          <button type="button" class="btn btn-sm btn-accent" data-prompt="${p.id}">Run brand check</button>
        </article>`
        )
        .join("")}
    </div>`;
    $("guardRight").querySelectorAll("[data-prompt]").forEach((btn) => {
      btn.addEventListener("click", () => toast("Brand check passed · prompt locked for generation"));
    });
    $("guardRaci").innerHTML = `<div class="card-head"><div><h2>RACI · human-in-the-loop</h2><p>Automation never bypasses publish authority</p></div></div>
      <div class="raci-grid pad">${g.raci
        .map(
          (row) => `<div class="raci-row"><strong>${row.step}</strong>
          <span>R · ${row.r}</span><span>A · ${row.a}</span><span>C · ${row.c}</span><span>I · ${row.i}</span></div>`
        )
        .join("")}</div>`;
  }

  function renderPerformance() {
    $("perfBoard").innerHTML = `<div class="perf-context card soft-inset">
        <div class="fc-label">Industry context (cited)</div>
        <p>Retail media fragmentation, AI creative speed, and disclosure enforcement reshape what “good performance” means — CTR alone is not enough without governable creative ops.</p>
        <div class="chip-row">${["Skai RMN sprawl", "Kantar CES trust", "Walmart Connect ACG", "FTC / NY disclosure"]
          .map((t) => `<span class="chip chip-muted">${t}</span>`)
          .join("")}</div>
      </div>
      <div class="perf-grid">${D()
        .performance.map(
          (p) => `<article class="perf-card">
        <div class="fc-label">${p.name}</div>
        <div class="perf-metrics">
          <div><strong>${p.ctr}</strong><span>CTR</span></div>
          <div><strong>${p.eng}</strong><span>Engagement</span></div>
          <div><strong>${p.cpa}</strong><span>CPA</span></div>
        </div>
        <p><strong>Learning:</strong> ${p.learnings}</p>
        ${p.industryNote ? `<p class="news-act"><strong>Market:</strong> ${p.industryNote}</p>` : ""}
        <p class="page-sub">Next brief → ${p.next}</p>
        ${
          p.briefId && D().briefs.find((b) => b.id === p.briefId)
            ? `<button type="button" class="btn btn-sm btn-ghost" data-brief="${p.briefId}">Open brief</button>`
            : ""
        }
      </article>`
        )
        .join("")}</div>`;
    $("perfBoard").querySelectorAll("[data-brief]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.briefId = btn.getAttribute("data-brief");
        showPanel("briefs");
      });
    });
  }

  function renderAssets() {
    $("assetGrid").innerHTML = D()
      .assets.map((a) => {
        const sel = a.id === state.selectedAsset ? "selected" : "";
        return `<article class="asset-card ${sel}" data-id="${a.id}" data-brief="${a.briefId}">
          <div class="asset-art"><strong>${a.name}</strong><span>${a.size}</span></div>
          <div class="banner-meta">
            <span class="chip ${a.status === "approved" ? "chip-ok" : "chip-muted"}">${a.status.replace(/_/g, " ")}</span>
            <span>${a.tags.join(" · ")}</span>
          </div>
        </article>`;
      })
      .join("");
    $("assetGrid").querySelectorAll(".asset-card").forEach((card) => {
      card.addEventListener("click", () => {
        state.selectedAsset = card.getAttribute("data-id");
        state.briefId = card.getAttribute("data-brief");
        renderAssets();
      });
    });
  }

  function renderInbox() {
    const mentions = D().inbox.filter((i) => (i.type || "mention") === "mention");
    $("inboxList").innerHTML =
      `<div class="inbox-section-label">Stakeholder mentions</div>` +
      mentions
        .map(
          (i) => `<div class="inbox-row ${i.status}">
        <div>
          <div class="t">${i.mention} <span class="page-sub">from ${i.from}</span></div>
          <div class="s">${i.text}</div>
        </div>
        <div class="inbox-side">
          <span class="chip ${i.status === "escalated" ? "chip-danger" : "chip-warn"}">${i.sla}</span>
          <button type="button" class="btn btn-sm btn-ghost" data-brief="${i.briefId}">Open</button>
        </div>
      </div>`
        )
        .join("") +
      `<div class="inbox-section-label">Industry news pulse · real public stories</div>` +
      D()
        .industryNews.map(
          (n) => `<div class="inbox-row news">
        <div>
          <div class="t">${n.title}</div>
          <div class="s">${n.takeaway}</div>
          <p class="news-act"><strong>GenAIForge next:</strong> ${n.forgeAction}</p>
          <p class="news-cite">${n.source} · ${n.date} · demo/illustrative citation</p>
        </div>
        <div class="inbox-side">
          <span class="chip chip-muted">News</span>
          ${
            n.briefHint
              ? `<button type="button" class="btn btn-sm btn-accent" data-brief="${n.briefHint}">Brief</button>`
              : `<button type="button" class="btn btn-sm btn-ghost" data-goto="roi">ROI</button>`
          }
        </div>
      </div>`
        )
        .join("");
    $("inboxList").querySelectorAll("[data-brief]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.briefId = btn.getAttribute("data-brief");
        showPanel("briefs");
      });
    });
    $("inboxList").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });
  }

  function renderRoi() {
    const r = D().roi;
    $("roiBoard").innerHTML = `
      <div class="card hero-pitch"><div class="hero-inner">
        <p class="hero-eyebrow">Why buy · business case</p>
        <h2>${r.headline}</h2>
        <div class="hero-proof">${r.metrics
          .map((m) => `<div><strong>${m.value}</strong><span>${m.label}</span><em>${m.note}</em></div>`)
          .join("")}</div>
      </div></div>
      <div class="card"><div class="card-head"><div><h2>Cost vs agency</h2><p>Illustrative pack economics</p></div></div>
        <div class="cost-table">${r.costCompare
          .map(
            (c) => `<div class="cost-row"><span>${c.label}</span><span>Agency ${c.agency}</span><span>Studio ${c.studio}</span><strong>Save ${c.save}</strong></div>`
          )
          .join("")}</div>
      </div>
      <div class="split">
        <div class="card"><div class="card-head"><div><h2>What you get</h2><p>Pilot / Production</p></div></div>
          <div class="pkg-grid pad">${r.packages
            .map(
              (p) => `<article class="pkg-card"><h3>${p.name}</h3><div class="page-sub">${p.price}</div><ul>${p.points
                .map((x) => `<li>${x}</li>`)
                .join("")}</ul></article>`
            )
            .join("")}</div>
        </div>
        <div class="card"><div class="card-head"><div><h2>Trust &amp; FAQ</h2><p>Demo-labeled claims</p></div></div>
          <div class="pad">
            <div class="chip-row">${r.trust.map((t) => `<span class="chip chip-muted">${t}</span>`).join("")}</div>
            <div class="chip-row" style="margin-top:0.75rem">${r.integrations
              .map((i) => `<span class="chip">${i}</span>`)
              .join("")}</div>
            <div class="faq-list">${r.faq
              .map((f) => `<details><summary>${f.q}</summary><p>${f.a}</p></details>`)
              .join("")}</div>
            <div class="row-actions" style="padding:0.75rem 0 0">
              <button type="button" class="btn btn-accent" id="auditExportBtn">Export audit sample</button>
              <button type="button" class="btn btn-ghost" data-goto="approvals">See HITL gates</button>
            </div>
          </div>
        </div>
      </div>`;
    $("roiBoard").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });
    $("auditExportBtn").addEventListener("click", () => toast("Audit CSV exported · creatives_audit_sample.csv (demo)"));
  }

  function renderBriefList() {
    $("briefListMeta").textContent = `${D().briefs.length} campaigns`;
    $("briefList").innerHTML = D()
      .briefs.map((b) => {
        const st = D().stages.find((s) => s.id === b.stage);
        return `<li data-id="${b.id}" class="${b.id === state.briefId ? "active" : ""}">
        <div>
          <div class="t">${b.name}</div>
          <div class="s">${b.product} · ${b.budget}</div>
          <div class="li-chips">
            <span class="chip ${statusChip(b.status)}">${b.status.replace(/_/g, " ")}</span>
            <span class="chip chip-muted">${st ? st.label : b.stage}</span>
          </div>
        </div>
      </li>`;
      })
      .join("");
    $("briefList").querySelectorAll("li").forEach((li) => {
      li.addEventListener("click", () => {
        state.briefId = li.getAttribute("data-id");
        state.selectedBanner = null;
        renderPanel();
      });
    });
  }

  function renderBriefDetail() {
    const b = brief();
    const idx = stageIndex(b.stage);
    $("briefTitle").textContent = b.name;
    $("briefMeta").textContent = `${b.product} · ${b.size} · ${b.budget}`;
    $("briefStatus").textContent = b.status.replace(/_/g, " ");
    $("briefStatus").className = "chip " + statusChip(b.status);

    $("stageRail").innerHTML = D()
      .stages.map((s, i) => {
        const cls = i < idx ? "done" : i === idx ? "active" : "";
        return `<div class="stage-dot ${cls}"><span class="n">${i + 1}</span>${s.label}</div>`;
      })
      .join("");

    $("briefFields").innerHTML = [
      ["Goal", b.goal],
      ["Audience", b.audience],
      ["Platforms", b.platforms],
      ["Offer", b.offer],
      ["KPI", b.kpi],
      ["Timeline", b.timeline],
      ["Mandatories", b.mandatories],
      b.inspiredBy ? ["Inspired by (cited)", b.inspiredBy] : null,
      ["Stage owner", D().stages[idx].owner + " · " + D().stages[idx].label],
    ]
      .filter(Boolean)
      .map(([k, v]) => `<div class="${k === "Mandatories" || k === "Goal" || k === "Inspired by (cited)" ? "span2" : ""}"><dt>${k}</dt><dd>${v}</dd></div>`)
      .join("");

    const comments = b.comments || [];
    $("briefComments").innerHTML =
      `<h4>Comments & activity</h4>` +
      (comments.length
        ? comments
            .map(
              (c) => `<div class="feed-item"><div class="av">${c.initials}</div><div>
          <div>${c.text}</div><div class="meta">${c.by} · ${c.at}</div></div></div>`
            )
            .join("")
        : `<div class="empty">No comments yet on this brief.</div>`);
  }

  function updateCharCounts() {
    const set = (id, el, soft) => {
      const n = el.value.length;
      const max = Number(el.getAttribute("maxlength") || 0);
      const node = $(id);
      node.textContent = `${n}/${max}`;
      node.className = "char-count" + (n > soft ? (n >= max ? " over" : " warn") : "");
    };
    set("hlCount", $("copyHeadline"), 60);
    set("bodyCount", $("copyBody"), 220);
    set("ctaCount", $("copyCta"), 28);
  }

  function renderCopies() {
    const q = D().queues[state.roleId] || { waiting: [], done: [] };
    const items = q[state.queueTab] || [];
    $("queueSub").textContent = `${role().title} · ${q.waiting.length} waiting · ${q.done.length} done`;
    $("copyBriefName").textContent = brief().name;

    document.querySelectorAll("#queueTabs .queue-tab").forEach((t) => {
      t.classList.toggle("active", t.getAttribute("data-q") === state.queueTab);
    });

    if (!items.length) {
      $("roleQueue").innerHTML = `<li class="empty" style="cursor:default">Nothing in ${state.queueTab}.</li>`;
    } else {
      $("roleQueue").innerHTML = items
        .map(
          (item) => `<li data-id="${item.briefId}" class="${item.briefId === state.briefId ? "active" : ""}">
          <div><div class="t">${item.title}</div><div class="s">${item.sub}</div>
          <div class="li-chips"><span class="chip chip-muted">${(item.stage || "").replace(/_/g, " ")}</span></div></div>
        </li>`
        )
        .join("");
      $("roleQueue").querySelectorAll("li[data-id]").forEach((li) => {
        li.addEventListener("click", () => {
          state.briefId = li.getAttribute("data-id");
          renderPanel();
        });
      });
    }

    const b = brief();
    const ai = b.copy.aiDraft;
    $("copyCompare").innerHTML = `
      <div class="compare-pane"><h4>AI draft</h4>
        <div class="hl">${ai.headline}</div>
        <div class="bd">${ai.body}</div>
        <div class="cta">${ai.cta}</div>
      </div>
      <div class="compare-pane"><h4>Current edit</h4>
        <div class="hl">${b.copy.headline}</div>
        <div class="bd">${b.copy.body}</div>
        <div class="cta">${b.copy.cta}</div>
      </div>`;

    $("copyHeadline").value = b.copy.headline;
    $("copyBody").value = b.copy.body;
    $("copyCta").value = b.copy.cta;
    updateCharCounts();

    $("versionList").innerHTML =
      `<li style="border:0;font-size:0.72rem;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.04em">Version history</li>` +
      (b.copy.versions || [])
        .slice()
        .reverse()
        .map(
          (v) => `<li><span><span class="v">v${v.v}</span> ${v.note}</span><span>${v.by} · ${v.at}</span></li>`
        )
        .join("");
  }

  function renderDesign() {
    const b = brief();
    $("designBriefName").textContent = `${b.name} · step ${state.designStep + 1} of ${DESIGN_STEPS.length}`;
    $("designStepper").innerHTML = DESIGN_STEPS.map((label, i) => {
      const cls = i < state.designStep ? "done" : i === state.designStep ? "active" : "";
      return `<button type="button" class="step-pill ${cls}" data-step="${i}">${i + 1}. ${label}</button>`;
    }).join("");
    $("designStepper").querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.designStep = Number(btn.getAttribute("data-step"));
        renderDesign();
      });
    });

    const body = $("designStepBody");
    if (state.designStep === 0) {
      body.innerHTML = `<div class="pad">
        <p class="page-sub" style="margin:0 0 0.75rem">Select a creative size to refine. Context: <strong>${b.copy.headline}</strong></p>
        <div class="design-board">${b.banners
          .map((bn) => {
            const sel = state.selectedBanner === bn.id ? "selected" : "";
            return `<article class="banner-card ${sel}" data-id="${bn.id}">
              <div class="banner-art"><strong>${b.copy.headline}</strong><span>${bn.template}</span></div>
              <div class="banner-meta"><span>${bn.label} · ${bn.size}</span><span class="chip chip-muted">${bn.status}</span></div>
            </article>`;
          })
          .join("")}</div>
        <div class="row-actions"><button type="button" class="btn btn-accent" id="designNext">Continue to Template</button></div>
      </div>`;
      body.querySelectorAll(".banner-card").forEach((card) => {
        card.addEventListener("click", () => {
          state.selectedBanner = card.getAttribute("data-id");
          renderDesign();
        });
      });
      $("designNext").addEventListener("click", () => {
        state.designStep = 1;
        renderDesign();
      });
    } else if (state.designStep === 1) {
      const templates = ["Performance hero", "Story strip", "Vertical offer", "Soft strip", "Co-brand hero"];
      body.innerHTML = `<div class="template-grid">${templates
        .map(
          (t) => `<div class="template-card ${t === state.selectedTemplate ? "active" : ""}" data-t="${t}">
          <strong>${t}</strong><div class="page-sub" style="margin-top:0.35rem">Layout system for ${b.product}</div></div>`
        )
        .join("")}</div>
        <div class="row-actions"><button type="button" class="btn btn-ghost" id="designBack">Back</button>
        <button type="button" class="btn btn-accent" id="designNext">Continue to Heroes</button></div>`;
      body.querySelectorAll(".template-card").forEach((card) => {
        card.addEventListener("click", () => {
          state.selectedTemplate = card.getAttribute("data-t");
          renderDesign();
        });
      });
      $("designBack").addEventListener("click", () => {
        state.designStep = 0;
        renderDesign();
      });
      $("designNext").addEventListener("click", () => {
        state.designStep = 2;
        renderDesign();
      });
    } else if (state.designStep === 2) {
      const thread = (b.designChat || [])
        .map((m) => `<div class="d-bubble ${m.role === "user" ? "user" : "ai"}">${m.text}</div>`)
        .join("");
      body.innerHTML = `<div class="design-board">${b.banners
        .map(
          (bn) => `<article class="banner-card">
          <div class="banner-art"><strong>${b.copy.headline}</strong><span>${state.selectedTemplate}</span></div>
          <div class="banner-meta"><span>${bn.size}</span><span>${bn.label}</span></div>
        </article>`
        )
        .join("")}</div>
        <div class="design-chat">
          <h3 style="margin:0 0 0.5rem;font-size:0.85rem">Refine with AI</h3>
          <div class="thread">${thread || `<div class="empty">No refine thread yet — try a prompt.</div>`}</div>
          <div class="row-actions" style="padding:0">
            <button type="button" class="btn btn-accent" id="refineHeroBtn">Refine hero lighting</button>
            <button type="button" class="btn btn-ghost" id="designBack">Back</button>
            <button type="button" class="btn btn-ghost" id="designNext">Continue to Export</button>
          </div>
        </div>`;
      $("refineHeroBtn").addEventListener("click", () => {
        b.designChat = b.designChat || [];
        b.designChat.push({ role: "user", text: "Warm lighting · tighter product crop" });
        b.designChat.push({
          role: "ai",
          text: "Applied warmer key light and 1.15× crop on " + state.selectedTemplate + ".",
        });
        pushActivity(b, "edit", "Ran AI hero refine");
        toast("AI refine applied · warmer lighting");
        renderDesign();
      });
      $("designBack").addEventListener("click", () => {
        state.designStep = 1;
        renderDesign();
      });
      $("designNext").addEventListener("click", () => {
        state.designStep = 3;
        renderDesign();
      });
    } else {
      body.innerHTML = `<div class="export-box">
        <p>Export pack for <strong>${b.name}</strong> using template <strong>${state.selectedTemplate}</strong>.</p>
        <ul style="color:var(--text-muted);font-size:0.85rem;line-height:1.6">
          ${b.banners.map((bn) => `<li>${bn.label} · ${bn.size} · ${bn.status}</li>`).join("")}
        </ul>
        <div class="row-actions" style="padding:0.5rem 0 0">
          <button type="button" class="btn btn-accent" id="exportBtn">Export ZIP (demo)</button>
          <button type="button" class="btn btn-ghost" id="designBack">Back</button>
          <button type="button" class="btn btn-ghost" data-goto="approvals">Send to Approvals</button>
        </div>
      </div>`;
      $("exportBtn").addEventListener("click", () => {
        pushActivity(b, "export", "Exported creative pack");
        toast("Export ready · creatives_" + b.id + ".zip (demo)");
      });
      $("designBack").addEventListener("click", () => {
        state.designStep = 2;
        renderDesign();
      });
      body.querySelectorAll("[data-goto]").forEach((btn) => {
        btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
      });
    }
  }

  function openReasonModal(gateKey, onConfirm) {
    const host = $("modalHost");
    host.innerHTML = `<div class="modal-backdrop" id="modalBg">
      <div class="modal" role="dialog" aria-modal="true">
        <h3>Request changes</h3>
        <p>Add a reason for ${GATE_LABELS[gateKey]} — shown in the activity feed.</p>
        <textarea id="reasonInput" placeholder="e.g. Disclaimer contrast too low on story size"></textarea>
        <div class="modal-actions">
          <button type="button" class="btn btn-ghost" id="reasonCancel">Cancel</button>
          <button type="button" class="btn btn-danger" id="reasonOk">Submit</button>
        </div>
      </div>
    </div>`;
    const close = () => {
      host.innerHTML = "";
    };
    $("reasonCancel").addEventListener("click", close);
    $("modalBg").addEventListener("click", (e) => {
      if (e.target.id === "modalBg") close();
    });
    $("reasonOk").addEventListener("click", () => {
      const note = $("reasonInput").value.trim() || "Changes requested (no note)";
      close();
      onConfirm(note);
    });
  }

  function renderGates() {
    const b = brief();
    $("gateBriefName").textContent = b.name;
    $("gates").innerHTML = Object.keys(GATE_LABELS)
      .map((key) => {
        const g = b.gates[key];
        const st = g.status;
        const canAct =
          st === "pending" && (state.roleId === "PL" || state.roleId === "ML" || key === "brief_review");
        const blocked = st === "blocked";
        const checks = (g.checklist || [])
          .map((c, i) => `<li class="${st === "approved" || i < 2 ? "on" : ""}">${c}</li>`)
          .join("");
        return `<article class="gate-card ${blocked ? "blocked" : ""}" data-gate="${key}">
          <h3>${GATE_LABELS[key]}</h3>
          <div class="gate-meta">Reviewer · ${g.reviewer}<br/>SLA · ${g.sla}</div>
          <div class="gate-state ${st}">${st.replace(/_/g, " ")}</div>
          <ul class="check-list">${checks}</ul>
          ${g.note ? `<p class="gate-meta">Note: ${g.note}</p>` : ""}
          <div class="gate-actions">
            <button type="button" class="btn btn-accent btn-sm" data-act="approve" ${canAct && !blocked ? "" : "disabled"}>Approve</button>
            <button type="button" class="btn btn-danger btn-sm" data-act="changes" ${canAct && !blocked ? "" : "disabled"}>Request changes</button>
          </div>
        </article>`;
      })
      .join("");

    $("gates").querySelectorAll(".gate-card").forEach((card) => {
      card.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          const key = card.getAttribute("data-gate");
          const act = btn.getAttribute("data-act");
          const apply = (note) => {
            if (act === "approve") {
              b.gates[key].status = "approved";
              b.gates[key].note = note || "Approved";
              pushActivity(b, "approve", "Approved " + GATE_LABELS[key]);
              if (key === "brief_review" && b.stage === "brief_review") b.stage = "copywriting";
              if (key === "creative_review" && b.stage === "creative_review") {
                b.stage = "final_signoff";
                if (b.gates.final_signoff.status === "blocked") b.gates.final_signoff.status = "pending";
              }
              if (key === "final_signoff") b.status = "approved";
              toast("Gate approved · " + GATE_LABELS[key]);
            } else {
              b.gates[key].status = "changes_requested";
              b.gates[key].note = note;
              pushActivity(b, "handoff", "Requested changes on " + GATE_LABELS[key] + ": " + note);
              toast("Changes requested");
            }
            updateNavBadges();
            renderPanel();
          };
          if (act === "changes") openReasonModal(key, apply);
          else apply("");
        });
      });
    });
  }

  function renderActivity() {
    const b = brief();
    $("activityBriefName").textContent = b.name;
    if (!b.activity.length) {
      $("timeline").innerHTML = `<li class="empty">No events yet.</li>`;
      return;
    }
    $("timeline").innerHTML = b.activity
      .map(
        (a) => `<li>
        <div class="tl-av">${a.initials || "·"}</div>
        <div>
          <span class="tl-type ${a.type || ""}">${a.type || "event"}</span>
          <strong>${a.actor || "System"}</strong> — ${a.text}
          <time>${a.at}</time>
        </div>
      </li>`
      )
      .join("");
  }

  function renderPanel() {
    updateNavBadges();
    if (state.panel === "home") renderHome();
    if (state.panel === "briefs") {
      renderBriefList();
      renderBriefDetail();
    }
    if (state.panel === "copies") renderCopies();
    if (state.panel === "design") renderDesign();
    if (state.panel === "approvals") renderGates();
    if (state.panel === "activity") renderActivity();
    if (state.panel === "calendar") renderCalendar();
    if (state.panel === "guardrails") renderGuardrails();
    if (state.panel === "performance") renderPerformance();
    if (state.panel === "assets") renderAssets();
    if (state.panel === "inbox") renderInbox();
    if (state.panel === "roi") renderRoi();
  }

  function boot() {
    if (!D()) {
      setTimeout(boot, 20);
      return;
    }
    applyTheme(isLight() ? "light" : "dark");
    $("themeToggle").addEventListener("click", () => applyTheme(isLight() ? "dark" : "light"));

    $("roleSelect").innerHTML = D()
      .roles.map((r) => `<option value="${r.id}">${r.title}</option>`)
      .join("");
    $("roleSelect").value = state.roleId;
    $("roleSelect").addEventListener("change", () => {
      state.roleId = $("roleSelect").value;
      renderPanel();
    });

    document.querySelectorAll(".nav-item").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-panel")));
    });
    document.querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });

    $("queueTabs").querySelectorAll(".queue-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        state.queueTab = tab.getAttribute("data-q");
        renderCopies();
      });
    });

    ["copyHeadline", "copyBody", "copyCta"].forEach((id) => {
      $(id).addEventListener("input", updateCharCounts);
    });

    $("advanceStageBtn").addEventListener("click", () => {
      const b = brief();
      const idx = stageIndex(b.stage);
      if (idx < D().stages.length - 1) {
        b.stage = D().stages[idx + 1].id;
        pushActivity(b, "handoff", "Advanced to " + D().stages[idx + 1].label);
        const rail = $("stageRail");
        if (rail) rail.classList.remove("pulse");
        toast("Moved to " + D().stages[idx + 1].label);
        renderPanel();
      } else toast("Already at final sign-off");
    });

    $("saveCopyBtn").addEventListener("click", () => {
      const b = brief();
      b.copy.headline = $("copyHeadline").value;
      b.copy.body = $("copyBody").value;
      b.copy.cta = $("copyCta").value;
      const nextV = (b.copy.versions.length ? b.copy.versions[b.copy.versions.length - 1].v : 0) + 1;
      b.copy.versions.push({ v: nextV, at: "Just now", by: role().name.split(" ")[0], note: "Manual save" });
      pushActivity(b, "edit", "Saved copy v" + nextV);
      toast("Copy saved · v" + nextV);
      renderPanel();
    });

    $("regenCopyBtn").addEventListener("click", () => {
      const b = brief();
      const variants = [
        {
          headline: "Festive payments, zero friction",
          body: "Top up once. Spend everywhere. Cashback that shows up before the weekend plans do.",
          cta: "Top up in-app",
        },
        {
          headline: "Make every celebration effortless",
          body: "ForgePay festive loads land cashback fast — built for metro evenings and last-minute gifts.",
          cta: "Claim festive cashback",
        },
      ];
      const pick = variants[Math.floor(Math.random() * variants.length)];
      b.copy.aiDraft = pick;
      toast("AI regenerated a fresh draft");
      pushActivity(b, "edit", "Regenerated AI copy draft");
      renderCopies();
    });

    const calExport = $("calExportBtn");
    if (calExport) {
      calExport.addEventListener("click", () => toast("Launch plan exported · calendar_plan.csv (demo)"));
    }
    const reuseBtn = $("reuseAssetBtn");
    if (reuseBtn) {
      reuseBtn.addEventListener("click", () => {
        const a = D().assets.find((x) => x.id === state.selectedAsset);
        if (a) {
          state.briefId = a.briefId;
          toast("Reused “" + a.name + "” into " + brief().name);
          showPanel("design");
        }
      });
    }

    showPanel("home");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
