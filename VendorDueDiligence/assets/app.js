/* GenAIForge VDD — Risk M2 command center */
(function () {
  "use strict";
  const D = () => window.VDD_DATA;
  const TITLES = {
    dashboard: ["Dashboard", "Register → screen → decide → monitor"],
    vendors: ["Vendors", "Searchable registry · summary drawer"],
    dd: ["Due Diligence", "Live run · score · decision"],
    report: ["Report", "Flags · findings · PDF · sign-off"],
    monitor: ["Monitoring", "Alerts · cadence · continuous risk"],
    forms: ["Questionnaires", "Assignment · progress · export"],
    scoring: ["Risk scoring", "Inherent vs residual · HITL accept"],
    controls: ["Controls", "Findings → policy mapping"],
    audit: ["Audit pack", "Examiner-ready export contents"],
    procurement: ["Procurement", "TPRM buyer checklist · packages"],
    m1: ["M1 Snapshot", "Outsourcing classification"],
  };
  const state = {
    panel: "dashboard",
    vendorId: "v1",
    step: -1,
    running: false,
    revealed: false,
    signedOff: false,
    tab: "overview",
    timerId: null,
    elapsed: 0,
    logs: [],
    search: "",
    band: "",
    country: "",
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
  function vendor() {
    return D().vendors.find((v) => v.id === state.vendorId);
  }
  function isLight() {
    return document.documentElement.classList.contains("gf-theme-light");
  }
  function applyTheme(mode) {
    document.documentElement.classList.remove("gf-theme-light", "gf-theme-dark");
    document.documentElement.classList.add(mode === "light" ? "gf-theme-light" : "gf-theme-dark");
    localStorage.setItem("gf-theme", mode === "light" ? "light" : "dark");
    const meta = $("themeColorMeta");
    if (meta) meta.content = mode === "light" ? "#f4f7f6" : "#0a1410";
  }
  function bandClass(b) {
    return "chip chip-" + String(b || "").toLowerCase();
  }
  function updateCtx() {
    const v = vendor();
    $("ctxVendor").textContent = v.short + " · " + v.risk_band;
    $("navVendors").textContent = String(D().vendors.length);
    const mon = $("navMonitor");
    if (mon) {
      mon.textContent = String(D().monitoring.filter((m) => m.severity !== "ok").length);
    }
  }

  function showPanel(id) {
    state.panel = id;
    document.querySelectorAll(".nav-item").forEach((b) =>
      b.classList.toggle("active", b.getAttribute("data-panel") === id)
    );
    document.querySelectorAll("[data-view]").forEach((v) => {
      v.hidden = v.id !== "view-" + id;
    });
    const t = TITLES[id];
    $("pageTitle").textContent = t[0];
    $("pageSub").textContent = t[1];
    renderPanel();
  }

  function selectVendor(id, resetRun) {
    state.vendorId = id;
    if (resetRun) {
      state.revealed = false;
      state.signedOff = false;
      state.step = -1;
      state.running = false;
      state.logs = [];
      clearInterval(state.timerId);
    }
    updateCtx();
    renderPanel();
  }

  function sparkSvg(values) {
    const w = 320;
    const h = 64;
    const max = Math.max.apply(null, values.concat([1]));
    const step = w / (values.length - 1);
    const pts = values
      .map((n, i) => {
        const x = i * step;
        const y = h - 8 - (n / max) * (h - 16);
        return x + "," + y;
      })
      .join(" ");
    const area = "0," + h + " " + pts + " " + w + "," + h;
    return `<svg class="spark-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
      <defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.35"/>
        <stop offset="100%" stop-color="var(--accent)" stop-opacity="0"/>
      </linearGradient></defs>
      <polygon fill="url(#sg)" points="${area}"/>
      <polyline fill="none" stroke="var(--accent)" stroke-width="2.5" points="${pts}"/>
    </svg>`;
  }

  function renderDashboard() {
    $("narrativeRail").innerHTML = D()
      .narrative.map((s, i) => {
        const panels = ["vendors", "dd", "report", "monitor"];
        return `<button type="button" class="narr-step" data-goto="${panels[i]}"><span>${i + 1}</span>${s}</button>`;
      })
      .join("") + `<span class="narr-arrow">→</span>`;
    $("narrativeRail").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });

    $("kpiRow").innerHTML = [
      [D().stats.vendors, "Vendors on file"],
      [D().stats.open, "Open DD runs"],
      [D().stats.signoff, "Awaiting sign-off"],
      [D().monitoring.filter((m) => m.severity === "critical").length, "Critical alerts"],
    ]
      .map(([n, l]) => `<div class="kpi"><strong>${n}</strong><span>${l}</span></div>`)
      .join("");

    const maxBand = Math.max.apply(
      null,
      D().stats.riskBands.map((b) => b.count).concat([1])
    );
    $("bandBars").innerHTML = D()
      .stats.riskBands.map(
        (b) => `<div class="band-row">
        <span>${b.label}</span>
        <div class="band-track"><div class="band-fill" style="width:${(b.count / maxBand) * 100}%;background:${b.color}"></div></div>
        <strong>${b.count}</strong>
      </div>`
      )
      .join("");

    $("sparkHost").innerHTML = sparkSvg(D().stats.spark14);

    const tb = $("recentTable").querySelector("tbody");
    tb.innerHTML = D()
      .recentRuns.map(
        (r) => `<tr data-id="${r.vendorId}">
        <td>${r.vendor}</td><td>${r.at}</td><td>${r.score}</td><td>${r.decision}</td>
      </tr>`
      )
      .join("");
    tb.querySelectorAll("tr").forEach((tr) => {
      tr.addEventListener("click", () => {
        selectVendor(tr.getAttribute("data-id"), true);
        showPanel("vendors");
      });
    });

    const b = D().buyer;
    $("dashBuyer").innerHTML = `<div class="card-head"><div><h2>Why buy · continuous TPRM</h2><p>${b.pitch}</p></div>
      <button type="button" class="btn btn-accent btn-sm" data-goto="procurement">Open buyer view</button></div>
      <div class="pad">
        <div class="chip-row">${b.trust.map((t) => `<span class="pill">${t}</span>`).join("")}</div>
        <div class="chip-row" style="margin-top:0.55rem">${b.integrations.map((i) => `<span class="pill">${i}</span>`).join("")}</div>
      </div>`;
    $("dashBuyer").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });

    $("themeFeed").innerHTML = D()
      .industryThemes.map(
        (t) => `<article class="theme-card">
        <div class="chip-row"><span class="pill">${t.source}</span></div>
        <strong>${t.title}</strong>
        <p class="muted">${t.takeaway}</p>
        <p><strong>GenAIForge:</strong> ${t.forgeAction}</p>
        <p class="muted" style="font-size:0.68rem">Demo / illustrative citation</p>
      </article>`
      )
      .join("");
  }

  function filteredVendors() {
    const q = state.search.trim().toLowerCase();
    return D().vendors.filter((v) => {
      if (state.band && v.risk_band !== state.band) return false;
      if (state.country && v.country !== state.country) return false;
      if (!q) return true;
      return (
        v.legal_name.toLowerCase().includes(q) ||
        v.cin.toLowerCase().includes(q) ||
        v.city.toLowerCase().includes(q) ||
        v.category.toLowerCase().includes(q)
      );
    });
  }

  function renderVendors() {
    const list = filteredVendors();
    $("vendorFilterMeta").textContent = `${list.length} of ${D().vendors.length} vendors`;
    const tb = $("vendorTable").querySelector("tbody");
    if (!list.length) {
      tb.innerHTML = `<tr><td colspan="5" class="empty">No vendors match filters.</td></tr>`;
    } else {
      tb.innerHTML = list
        .map(
          (v) => `<tr data-id="${v.id}" class="${v.id === state.vendorId ? "active" : ""}">
          <td>${v.legal_name}</td>
          <td><span class="${bandClass(v.risk_band)}">${v.risk_band}</span></td>
          <td>${v.country}</td>
          <td>${v.category}</td>
          <td>${v.status.replace(/_/g, " ")}</td>
        </tr>`
        )
        .join("");
      tb.querySelectorAll("tr[data-id]").forEach((tr) => {
        tr.addEventListener("click", () => selectVendor(tr.getAttribute("data-id"), true));
      });
    }

    const v = vendor();
    $("vendorDrawer").innerHTML = `<div class="drawer">
      <h3>${v.legal_name}</h3>
      <div class="drawer-meta">${v.website} · ${v.city}, ${v.country}</div>
      <span class="${bandClass(v.risk_band)}">${v.risk_band} risk</span>
      <dl style="margin-top:0.85rem">
        <div><dt>CIN / ID</dt><dd>${v.cin}</dd></div>
        <div><dt>Category</dt><dd>${v.category}</dd></div>
        <div><dt>Owner</dt><dd>${v.owner}</dd></div>
        <div><dt>Last screened</dt><dd>${v.last_screened}</dd></div>
        <div><dt>Status</dt><dd>${v.status.replace(/_/g, " ")}</dd></div>
        <div><dt>Prior score</dt><dd>${v.audit.score} · ${v.audit.decision}</dd></div>
      </dl>
      <div class="row-actions" style="padding:0.85rem 0 0">
        <button type="button" class="btn btn-accent" data-goto="dd">Screen this vendor</button>
        <button type="button" class="btn btn-ghost" data-goto="m1">M1 snapshot</button>
      </div>
    </div>`;
    $("vendorDrawer").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });
  }

  function renderSteps() {
    const pct = state.step < 0 ? 0 : Math.min(100, Math.round((state.step / D().steps.length) * 100));
    $("ddPct").textContent = pct + "%";
    $("ddProgress").style.width = pct + "%";
    $("ddSteps").innerHTML = D()
      .steps.map((label, i) => {
        let cls = "";
        if (i < state.step) cls = "done";
        else if (i === state.step) cls = "active";
        const log =
          i < state.step || (i === state.step && state.running)
            ? `<span class="step-log">${D().stepLogs[i]}</span>`
            : "";
        return `<li class="${cls}"><span class="dot"></span><div>${label}${log}</div></li>`;
      })
      .join("");
    if (state.logs.length) {
      $("runLog").hidden = false;
      $("runLog").innerHTML = state.logs.map((l) => `<div>${l}</div>`).join("");
      $("runLog").scrollTop = $("runLog").scrollHeight;
    } else {
      $("runLog").hidden = true;
    }
  }

  function renderDd() {
    const v = vendor();
    $("ddVendorName").textContent = v.legal_name;
    $("ddVendorMeta").textContent = `${v.website} · ${v.cin} · ${v.risk_band} band`;
    renderSteps();
    if (state.revealed) {
      const a = v.audit;
      $("scoreCard").hidden = false;
      $("scoreNum").textContent = String(a.score);
      $("scoreRating").textContent = a.rating + " risk";
      $("scoreDecision").textContent = a.decision;
      $("scoreDecision").className =
        "score-decision " +
        (a.decision === "Reject" ? "reject" : a.decision === "Conditional" ? "conditional" : "approve");
      $("scoreSummary").textContent = a.summary;
      $("bandNeedle").style.left = a.score + "%";
      $("bandLegend").innerHTML = D()
        .bands.map((b) => `<span style="border-left:3px solid ${b.color};padding-left:0.4rem">${b.label}</span>`)
        .join("");
      $("conditionsList").innerHTML = a.conditions.length
        ? a.conditions.map((c) => `<li>${c}</li>`).join("")
        : `<li>No conditions — decision is clean approve/reject.</li>`;
      $("signoffBtn").disabled = state.signedOff;
      $("reportSuggest").hidden = false;
    } else {
      $("scoreCard").hidden = true;
      $("signoffBtn").disabled = true;
      $("reportSuggest").hidden = true;
    }
  }

  function renderTab() {
    if (!state.revealed) {
      $("tabBody").innerHTML = `<p class="muted">Run screening on the Due Diligence panel first.</p>`;
      return;
    }
    const a = vendor().audit;
    if (state.tab === "overview") {
      $("tabBody").innerHTML = `<p>${a.overview}</p>
        <p style="margin-top:0.75rem"><strong>Decision:</strong> ${a.decision} · score ${a.score}</p>
        <p><strong>Conditions:</strong> ${a.conditions.length ? a.conditions.join(" · ") : "None"}</p>`;
    } else if (state.tab === "legal") {
      $("tabBody").innerHTML = `<p>${a.legal}</p>`;
    } else if (state.tab === "compliance") {
      $("tabBody").innerHTML = a.compliance.map((c) => `<span class="pill">${c}</span>`).join(" ");
    } else {
      $("tabBody").innerHTML = `<table class="findings-table"><thead><tr><th>Category</th><th>Finding</th><th>Disposition</th></tr></thead><tbody>${a.findings
        .map(
          (f) => `<tr>
          <td><span class="pill">${f.category.replace(/_/g, " ")}</span></td>
          <td>${f.title}</td>
          <td class="disp-${f.disposition}">${f.disposition}</td>
        </tr>`
        )
        .join("")}</tbody></table>`;
    }
  }

  function renderReport() {
    $("reportVendorName").textContent = vendor().legal_name;
    if (state.revealed) {
      const a = vendor().audit;
      $("redFlags").innerHTML = (a.red_flags.length ? a.red_flags : ["None material"])
        .map((f) => `<div class="flag-item danger"><div class="flag-icon">!</div><div>${f}</div></div>`)
        .join("");
      $("greenFlags").innerHTML = a.green_flags
        .map((f) => `<div class="flag-item ok"><div class="flag-icon">✓</div><div>${f}</div></div>`)
        .join("");
    } else {
      $("redFlags").innerHTML = `<div class="empty">No run yet</div>`;
      $("greenFlags").innerHTML = `<div class="empty">No run yet</div>`;
    }
    renderTab();
    $("signoffState").innerHTML = state.signedOff
      ? `<div class="signoff-banner">Signed off · ${vendor().legal_name} · demo attestation recorded</div>`
      : "";
  }

  function renderM1() {
    const v = vendor();
    const m = v.m1;
    const pct = Math.round(m.confidence * 100);
    $("m1Row").innerHTML = `
      <div>
        <div class="muted">Vendor</div>
        <strong>${v.legal_name}</strong>
        <div class="muted" style="margin-top:0.85rem">Classification label</div>
        <div class="m1-label">${m.label.replace(/_/g, " ")}</div>
        <div class="muted">Confidence · ${pct}%</div>
        <div class="conf-track"><div class="conf-fill" style="width:${pct}%"></div></div>
        <div class="muted">Regulator library</div>
        <div style="font-weight:650;margin-top:0.25rem">${m.regulator}</div>
      </div>
      <div>
        <div class="muted" style="margin-bottom:0.45rem">Evidence bullets (dummy)</div>
        <ul class="evidence">${(m.evidence || []).map((e) => `<li>${e}</li>`).join("")}</ul>
      </div>`;
  }

  function renderMonitor() {
    $("monitorList").innerHTML = D()
      .monitoring.map((m) => {
        const v = D().vendors.find((x) => x.id === m.vendorId);
        const active = m.vendorId === state.vendorId ? "active" : "";
        return `<button type="button" class="monitor-row ${m.severity} ${active}" data-id="${m.vendorId}">
          <div>
            <div class="t">${v ? v.short : m.vendorId} · ${m.alert}</div>
            <div class="s">${m.cadence} · ${m.at}${m.theme ? " · " + m.theme : ""}</div>
          </div>
          <span class="chip chip-${m.severity === "ok" ? "low" : m.severity === "warn" ? "medium" : "critical"}">${m.severity}</span>
        </button>`;
      })
      .join("");
    $("monitorList").querySelectorAll(".monitor-row").forEach((row) => {
      row.addEventListener("click", () => selectVendor(row.getAttribute("data-id"), false));
    });
  }

  function renderForms() {
    const list = D().questionnaires.filter((q) => q.vendorId === state.vendorId);
    const show = list.length ? list : D().questionnaires;
    $("formsMeta").textContent = `${show.length} forms · context ${vendor().short}`;
    $("formsList").innerHTML = show
      .map((q) => {
        const v = D().vendors.find((x) => x.id === q.vendorId);
        return `<div class="form-row">
          <div>
            <div class="t">${q.name}</div>
            <div class="s">${v ? v.short : ""} · ${q.assignee} · ${q.due}</div>
            <div class="prog-track"><div class="prog-fill" style="width:${q.progress}%"></div></div>
          </div>
          <div class="form-side">
            <span class="chip">${q.status.replace(/_/g, " ")}</span>
            <button type="button" class="btn btn-sm btn-ghost" data-id="${q.vendorId}">Select vendor</button>
          </div>
        </div>`;
      })
      .join("");
    $("formsList").querySelectorAll("[data-id]").forEach((btn) => {
      btn.addEventListener("click", () => selectVendor(btn.getAttribute("data-id"), false));
    });
  }

  function renderScoring() {
    const v = vendor();
    const residual = v.audit.score;
    const inherent = Math.max(0, Math.min(100, residual - (v.audit.conditions.length ? 14 : 8) + (v.audit.red_flags.length * 6)));
    const note = (D().residualNotes && D().residualNotes[v.id]) || "Residual acceptance requires analyst sign-off — automation never auto-approves Critical/High without HITL.";
    $("scoringBoard").innerHTML = `<div class="card-head"><div><h2>${v.legal_name}</h2><p>Inherent vs residual after controls · HITL acceptance (examiner-ready)</p></div>
      <button type="button" class="btn btn-accent btn-sm" id="acceptResidualBtn">Accept residual risk</button></div>
      <div class="score-gauges pad">
        <div class="gauge"><div class="gauge-label">Inherent</div><div class="gauge-ring" style="--p:${inherent}"><strong>${inherent}</strong></div><span>${inherent < 40 ? "Critical" : inherent < 60 ? "High" : inherent < 80 ? "Medium" : "Low"}</span></div>
        <div class="gauge"><div class="gauge-label">Residual</div><div class="gauge-ring residual" style="--p:${residual}"><strong>${residual}</strong></div><span>${v.audit.rating}</span></div>
      </div>
      <div class="pad">
        <p class="muted">Decision · <strong>${v.audit.decision}</strong></p>
        <ul class="conditions">${(v.audit.conditions.length ? v.audit.conditions : ["No open conditions"]).map((c) => `<li>${c}</li>`).join("")}</ul>
        <p class="muted" style="margin-top:0.75rem">${note}</p>
      </div>`;
    $("acceptResidualBtn").addEventListener("click", () => {
      state.signedOff = true;
      toast("Residual risk accepted · " + v.short + " (demo attestation)");
    });
  }

  function renderControls() {
    $("controlsList").innerHTML = `<div class="ctrl-table">
      <div class="ctrl-head"><span>Finding</span><span>Control</span><span>Frameworks</span></div>
      ${D()
        .controls.map(
          (c) => `<div class="ctrl-row"><span>${c.finding}</span><span>${c.control}</span>
          <span class="chip-row">${c.frameworks.map((f) => `<span class="pill">${f}</span>`).join("")}</span></div>`
        )
        .join("")}
    </div>
    <div class="pad"><button type="button" class="btn btn-ghost btn-sm" data-goto="report">Trace to Report findings</button></div>`;
    $("controlsList").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });
  }

  function renderAudit() {
    const v = vendor();
    $("auditBoard").innerHTML = `<div class="card-head"><div><h2>Audit pack · ${v.short}</h2><p>What the examiner / auditor gets</p></div>
      <button type="button" class="btn btn-accent" id="buildAuditBtn">Build ZIP</button></div>
      <div class="pad">
        <ol class="audit-ol">${D().auditPack.map((item) => `<li>${item}</li>`).join("")}</ol>
        <p class="muted">Includes run log for ${v.legal_name}, residual memo, and monitoring history. Demo-labeled · not a live filing.</p>
        <div class="chip-row" style="margin-top:0.75rem">
          <span class="pill">DORA-aligned export</span>
          <span class="pill">NIS2 evidence</span>
          <span class="pill">Timestamped decisions</span>
        </div>
      </div>`;
    $("buildAuditBtn").addEventListener("click", () =>
      toast("Audit pack queued · " + v.short + "_TPRM_audit.zip (demo)")
    );
  }

  function renderProcurement() {
    const b = D().buyer;
    const v = vendor();
    $("procBoard").innerHTML = `<div class="card-head"><div><h2>Procurement buyer view</h2><p>${b.pitch}</p></div></div>
      <div class="pad">
        <p class="muted">Checklist context · <strong>${v.short}</strong> · gap items are pitch hooks for Production</p>
        <div class="check-grid">${b.checklist
          .map(
            (c) => `<div class="check-item ${c.ok ? "ok" : "gap"}"><span>${c.ok ? "✓" : "!"}</span>${c.item}</div>`
          )
          .join("")}</div>
        <h3 style="margin:1.1rem 0 0.5rem;font-family:var(--font-display);font-size:1rem">Pilot vs Production</h3>
        <div class="pkg-row">${b.packages
          .map(
            (p) => `<article class="pkg"><h4>${p.name}</h4><ul>${p.points.map((x) => `<li>${x}</li>`).join("")}</ul></article>`
          )
          .join("")}</div>
        <h3 style="margin:1.1rem 0 0.5rem;font-family:var(--font-display);font-size:1rem">Trust &amp; integrations</h3>
        <div class="chip-row">${b.trust.concat(b.integrations).map((t) => `<span class="pill">${t}</span>`).join("")}</div>
        <div class="row-actions" style="padding:0.85rem 0 0">
          <button type="button" class="btn btn-accent" data-goto="dd">Run screening</button>
          <button type="button" class="btn btn-ghost" data-goto="audit">Preview audit pack</button>
          <button type="button" class="btn btn-ghost" data-goto="scoring">Inherent / residual</button>
        </div>
      </div>`;
    $("procBoard").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });
  }

  function renderPanel() {
    updateCtx();
    if (state.panel === "dashboard") renderDashboard();
    if (state.panel === "vendors") renderVendors();
    if (state.panel === "dd") renderDd();
    if (state.panel === "report") renderReport();
    if (state.panel === "m1") renderM1();
    if (state.panel === "monitor") renderMonitor();
    if (state.panel === "forms") renderForms();
    if (state.panel === "scoring") renderScoring();
    if (state.panel === "controls") renderControls();
    if (state.panel === "audit") renderAudit();
    if (state.panel === "procurement") renderProcurement();
  }

  function runScreening() {
    if (state.running) return;
    state.running = true;
    state.revealed = false;
    state.signedOff = false;
    state.step = 0;
    state.elapsed = 0;
    state.logs = ["[00:00] Screening started · " + vendor().legal_name];
    $("scoreCard").hidden = true;
    $("ddTimer").textContent = "Running · 0s";
    renderSteps();
    clearInterval(state.timerId);
    state.timerId = setInterval(() => {
      state.elapsed += 1;
      $("ddTimer").textContent = "Running · " + state.elapsed + "s";
    }, 1000);

    const tick = () => {
      const t = String(state.elapsed).padStart(2, "0");
      state.logs.push(`[00:${t}] ${D().stepLogs[Math.min(state.step, D().stepLogs.length - 1)]}`);
      renderSteps();
      if (state.step < D().steps.length - 1) {
        state.step += 1;
        setTimeout(tick, 520);
      } else {
        state.step = D().steps.length;
        renderSteps();
        clearInterval(state.timerId);
        $("ddTimer").textContent = "Complete · " + state.elapsed + "s";
        state.running = false;
        state.revealed = true;
        state.logs.push(`[00:${String(state.elapsed).padStart(2, "0")}] Score ready · open Report`);
        renderDd();
        toast("Screening complete · open Report for " + vendor().short);
      }
    };
    setTimeout(tick, 380);
  }

  function boot() {
    if (!D()) {
      setTimeout(boot, 20);
      return;
    }
    applyTheme(isLight() ? "light" : "dark");
    $("themeToggle").addEventListener("click", () => applyTheme(isLight() ? "dark" : "light"));
    document.querySelectorAll(".nav-item").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-panel")));
    });
    document.querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });
    $("runDdBtn").addEventListener("click", runScreening);
    $("signoffBtn").addEventListener("click", () => {
      state.signedOff = true;
      $("signoffBtn").disabled = true;
      toast("Signed off · " + vendor().legal_name);
      if (state.panel === "report") renderReport();
      else renderDd();
    });
    $("pdfBtn").addEventListener("click", () => {
      if (!state.revealed) {
        toast("Run screening first");
        return;
      }
      toast("PDF export queued · " + vendor().short + "_DD_report.pdf (demo)");
    });
    $("reportTabs").querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        state.tab = tab.getAttribute("data-tab");
        $("reportTabs").querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        renderTab();
      });
    });
    $("vendorSearch").addEventListener("input", () => {
      state.search = $("vendorSearch").value;
      renderVendors();
    });
    $("bandFilter").addEventListener("change", () => {
      state.band = $("bandFilter").value;
      renderVendors();
    });
    $("countryFilter").addEventListener("change", () => {
      state.country = $("countryFilter").value;
      renderVendors();
    });
    const ack = $("ackAlertBtn");
    if (ack) {
      ack.addEventListener("click", () => toast("Alerts acknowledged for " + vendor().short + " (demo)"));
    }
    const expForms = $("exportFormsBtn");
    if (expForms) {
      expForms.addEventListener("click", () => toast("Questionnaire pack exported · forms_" + vendor().short + ".zip (demo)"));
    }
    showPanel("dashboard");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
