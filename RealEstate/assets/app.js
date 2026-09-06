/* GenAIForge Real Estate — Sales Command Center */
(function () {
  "use strict";

  const D = () => window.RE_DATA;

  const state = {
    projectId: "pune",
    clusterId: null,
    selectedLeadId: null,
    callStep: 0,
    qualifierOpen: false,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function toast(msg) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove("show"), 2400);
  }

  function initials(name) {
    return name
      .split(" ")
      .map((p) => p[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();
  }

  function fmtMatchPct(score) {
    if (score == null) return "78%";
    return Math.min(96, Math.round(70 + score * 0.28)) + "%";
  }

  /* ——— Theme ——— */
  function isLight() {
    return document.documentElement.classList.contains("gf-theme-light");
  }

  function applyTheme(mode) {
    const root = document.documentElement;
    root.classList.remove("gf-theme-light", "gf-theme-dark");
    root.classList.add(mode === "light" ? "gf-theme-light" : "gf-theme-dark");
    localStorage.setItem("gf-theme", mode === "light" ? "light" : "dark");
    const meta = $("themeColorMeta");
    if (meta) meta.content = mode === "light" ? "#f7f8fa" : "#0a0c10";
    const btn = $("themeToggle");
    if (btn) btn.setAttribute("aria-label", mode === "light" ? "Switch to dark mode" : "Switch to light mode");
  }

  function initTheme() {
    applyTheme(isLight() ? "light" : "dark");
    $("themeToggle").addEventListener("click", () => {
      applyTheme(isLight() ? "dark" : "light");
      renderSitePlan();
    });
  }

  /* ——— Projects ——— */
  function initTabs() {
    const nav = $("projectTabs");
    nav.innerHTML = D()
      .projects.map(
        (p) =>
          `<button type="button" class="project-tab ${p.id === state.projectId ? "active" : ""}" data-id="${p.id}">${p.city}</button>`
      )
      .join("");
    nav.querySelectorAll(".project-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.projectId = btn.dataset.id;
        state.callStep = 0;
        nav.querySelectorAll(".project-tab").forEach((b) => b.classList.toggle("active", b.dataset.id === state.projectId));
        const clusters = D().interestClusters[state.projectId] || [];
        const hottest = [...clusters].sort((a, b) => b.interestCount - a.interestCount)[0];
        state.clusterId = hottest?.id || null;
        renderAll();
      });
    });
  }

  function renderHero() {
    const project = D().projects.find((p) => p.id === state.projectId);
    const k = D().kpis[state.projectId];
    const media = $("heroMedia");
    media.style.backgroundImage = `url("${project.heroImage}"), ${project.heroFallback}`;
    $("heroCity").textContent = project.city;
    $("heroTitle").textContent = project.name;
    $("heroTag").textContent = project.tagline;
    $("speedChip").textContent = `<60s · ${k.speedSec}s avg`;
    $("heroProof").textContent = `${k.leadsToday} leads today · ${k.qualifiedRate}% qualified · ${k.visitsBooked} visits booked`;
  }

  /* ——— Site plan ——— */
  function heatFill(heat) {
    if (heat === "high") return "var(--heat-high)";
    if (heat === "mid") return "var(--heat-mid)";
    return "var(--heat-low)";
  }

  function renderSitePlan() {
    const plan = D().sitePlans[state.projectId];
    const clusters = D().interestClusters[state.projectId] || [];
    const byTower = {};
    clusters.forEach((c) => {
      if (!byTower[c.towerId] || c.interestCount > byTower[c.towerId].interestCount) {
        byTower[c.towerId] = c;
      }
    });

    const towers = plan.towers
      .map((t) => {
        const c = byTower[t.id];
        const active = c && c.id === state.clusterId;
        const pulse = c && c.heat === "high" ? "pulse-hot" : "";
        const r = c ? 28 + Math.min(42, c.interestCount * 1.6) : 24;
        const cx = t.x + t.w / 2;
        const cy = t.y + t.h / 2;
        const visitRing = c?.visitToday
          ? `<circle cx="${cx}" cy="${cy}" r="${r + 8}" fill="none" stroke="#5dcaa5" stroke-width="2.5" opacity="0.9"/>`
          : "";
        return `
        <g class="heat-zone ${active ? "active" : ""} ${pulse}" data-cluster="${c?.id || ""}" data-tower="${t.id}">
          <rect x="${t.x}" y="${t.y}" width="${t.w}" height="${t.h}" rx="10"
            fill="var(--plan-tower)" stroke="var(--plan-tower-stroke)" stroke-width="1.5"/>
          <text x="${t.x + 12}" y="${t.y + 22}" class="heat-label" opacity="0.7">${t.label}</text>
          ${
            c
              ? `${visitRing}
            <circle class="heat-blob" cx="${cx}" cy="${cy}" r="${r}" fill="${heatFill(c.heat)}" opacity="0.9"/>
            <text class="heat-count" x="${cx}" y="${cy + 2}" text-anchor="middle" dominant-baseline="middle">${c.interestCount}</text>
            <text class="heat-label" x="${cx}" y="${cy + r + 16}" text-anchor="middle">${c.unitType}</text>`
              : ""
          }
        </g>`;
      })
      .join("");

    const labels = plan.labels
      .map((l) => `<text x="${l.x}" y="${l.y}" class="heat-label" opacity="0.45">${l.text}</text>`)
      .join("");

    const amen = plan.amenity;
    $("sitePlan").innerHTML = `
      <svg viewBox="0 0 800 480" preserveAspectRatio="xMidYMid meet">
        <rect width="800" height="480" fill="var(--plan-bg)"/>
        <path d="M40 40 H760 V440 H40 Z" fill="none" stroke="var(--plan-road)" stroke-width="2" stroke-dasharray="8 6"/>
        <path d="M40 280 H760 M280 40 V440" stroke="var(--plan-road)" stroke-width="10" opacity="0.5"/>
        <rect x="${amen.x}" y="${amen.y}" width="${amen.w}" height="${amen.h}" rx="8"
          fill="var(--plan-tower)" stroke="var(--plan-tower-stroke)" stroke-width="1"/>
        <text x="${amen.x + amen.w / 2}" y="${amen.y + amen.h / 2 + 4}" text-anchor="middle" class="heat-label" opacity="0.55">${amen.label}</text>
        ${labels}
        ${towers}
      </svg>`;

    $("sitePlan").querySelectorAll(".heat-zone").forEach((g) => {
      g.addEventListener("click", () => {
        const id = g.dataset.cluster;
        if (!id) return;
        state.clusterId = id;
        renderSitePlan();
        renderMatch();
        $("matchStrip").scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    });
  }

  function renderMatch() {
    const clusters = D().interestClusters[state.projectId] || [];
    const cluster = clusters.find((c) => c.id === state.clusterId) || clusters[0];
    if (!cluster) {
      $("matchTitle").textContent = "Match intelligence";
      $("matchSub").textContent = "No clusters for this project";
      $("buyerList").innerHTML = "";
      $("inventoryList").innerHTML = "";
      return;
    }
    state.clusterId = cluster.id;

    $("matchTitle").textContent = cluster.label;
    $("matchSub").textContent = `${cluster.interestCount} buyers interested · right customer → right unit`;
    $("matchCount").textContent = `${cluster.interestCount} interested`;

    const buyers = cluster.leadIds.map((id) => D().leads[id]).filter(Boolean);
    buyers.sort((a, b) => (b.score || 0) - (a.score || 0));

    $("buyerList").innerHTML = buyers
      .map(
        (b) => `
      <div class="buyer-card" data-lead="${b.id}">
        <div class="buyer-top">
          <div class="avatar">${initials(b.name)}</div>
          <div>
            <div class="buyer-name">${b.name}</div>
            <div class="buyer-meta">${b.lang} · ${b.source}</div>
          </div>
          <span class="temp temp-${b.temp}">${b.temp}</span>
        </div>
        <div class="buyer-meta">${b.budget} · ${b.intent} · ${b.timeline}${b.score != null ? ` · score ${b.score}` : ""}</div>
      </div>`
      )
      .join("");

    $("buyerList").querySelectorAll(".buyer-card").forEach((card) => {
      card.addEventListener("click", () => {
        state.selectedLeadId = card.dataset.lead;
        openQualifier(card.dataset.lead);
      });
    });

    const units = cluster.inventoryIds.map((id) => D().inventory[id]).filter(Boolean);
    $("inventoryList").innerHTML = units
      .map((u, i) => {
        const pct = fmtMatchPct(buyers[i]?.score ?? buyers[0]?.score);
        return `
        <div class="inv-card" data-inv="${u.id}">
          <img class="inv-photo" src="${u.image}" alt="" loading="lazy"
            onerror="this.style.opacity='0.3'"/>
          <div>
            <div class="inv-name">${u.unit} · ${u.type}</div>
            <div class="inv-meta">${u.tower} · ${u.price} · ${u.status}</div>
            <div class="inv-meta">${u.matchHint}</div>
            <div class="inv-actions">
              <span class="match-pct">${pct} match</span>
              <button type="button" class="btn btn-sm btn-accent assign-visit" data-inv="${u.id}">Assign visit</button>
            </div>
          </div>
        </div>`;
      })
      .join("");

    $("inventoryList").querySelectorAll(".assign-visit").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        toast(`Visit assigned for ${btn.dataset.inv} — CRM updated (demo)`);
        openQualifier(buyers[0]?.id);
      });
    });
  }

  /* ——— Live call ——— */
  function buildWaveform() {
    const w = $("waveform");
    w.innerHTML = Array.from({ length: 48 }, (_, i) => {
      const delay = (i % 12) * 0.08;
      return `<span style="animation-delay:${delay}s;height:${20 + (i % 7) * 10}%"></span>`;
    }).join("");
  }

  function renderLiveCall() {
    const call = D().liveCall[state.projectId];
    const lead = D().leads[call.leadId];
    $("liveTitle").textContent = `${lead.name} · Qualify`;
    $("liveMeta").textContent = `${call.lang} · ${lead.source} · ${call.intent}`;

    const steps = call.steps.slice(0, state.callStep + 1);
    $("transcript").innerHTML = steps
      .map(
        (s) => `
      <div class="bubble ${s.speaker}">
        <span class="who">${s.speaker === "agent" ? "Voice agent" : "Buyer"}</span>
        ${s.text}
      </div>`
      )
      .join("");
    $("transcript").scrollTop = $("transcript").scrollHeight;

    const nextBtn = $("liveNext");
    if (state.callStep >= call.steps.length - 1) {
      nextBtn.textContent = "Visit booked ✓";
      nextBtn.disabled = true;
    } else {
      nextBtn.textContent = "Advance conversation";
      nextBtn.disabled = false;
    }
  }

  function initLiveCall() {
    buildWaveform();
    $("liveNext").addEventListener("click", () => {
      const call = D().liveCall[state.projectId];
      if (state.callStep < call.steps.length - 1) {
        state.callStep += 1;
        renderLiveCall();
        if (state.callStep === call.steps.length - 1) {
          toast("Site visit booked · CRM updated (demo)");
        }
      }
    });
    $("liveReset").addEventListener("click", () => {
      state.callStep = 0;
      renderLiveCall();
    });
    $("watchLiveBtn").addEventListener("click", () => {
      $("liveCall").scrollIntoView({ behavior: "smooth", block: "center" });
      state.callStep = 0;
      renderLiveCall();
    });
    $("scrollMatchBtn").addEventListener("click", () => {
      $("matchStrip").scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  /* ——— Visits ——— */
  function renderVisits() {
    const visits = D().visits[state.projectId] || [];
    $("visitSummary").textContent = `${visits.length} today · reminders on`;
    $("visitTrack").innerHTML = visits
      .map((v) => {
        const lead = D().leads[v.leadId];
        const unit = D().inventory[v.unitId];
        return `
        <div class="visit-card" data-lead="${v.leadId}">
          <div class="visit-time">${v.time}</div>
          <div class="visit-name">${lead?.name || "Buyer"}</div>
          <div class="visit-unit">${unit ? `${unit.unit} · ${unit.type}` : v.unitId}</div>
          <span class="visit-status ${v.status}">${v.status} · ${v.reminder}</span>
        </div>`;
      })
      .join("");

    $("visitTrack").querySelectorAll(".visit-card").forEach((card) => {
      card.addEventListener("click", () => openQualifier(card.dataset.lead));
    });
  }

  /* ——— Qualifier ——— */
  function formatMsg(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  function appendMsg(role, text) {
    const box = $("qualifierMessages");
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.innerHTML = formatMsg(text);
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  function replyFor(q) {
    const scripts = D().qualifier.scripts;
    for (const key of Object.keys(scripts)) {
      if (key === "default") continue;
      if (scripts[key].match && scripts[key].match.test(q)) return scripts[key].reply;
    }
    return scripts.default.reply;
  }

  function openQualifier(leadId) {
    state.qualifierOpen = true;
    state.selectedLeadId = leadId || state.selectedLeadId;
    $("qualifier").hidden = false;
    $("qualifierBackdrop").hidden = false;

    const lead = state.selectedLeadId ? D().leads[state.selectedLeadId] : null;
    $("qualifierLead").textContent = lead
      ? `${lead.name} · ${lead.budget} · ${lead.intent} · ${lead.timeline}`
      : "No lead selected — ask to qualify or match inventory";

    $("qualifierMessages").innerHTML = "";
    appendMsg("bot", D().qualifier.welcome);

    $("qualifierSuggestions").innerHTML = D()
      .qualifier.suggestions.map((s) => `<button type="button" class="chip-btn" data-q="${s}">${s}</button>`)
      .join("");
    $("qualifierSuggestions").querySelectorAll(".chip-btn").forEach((chip) => {
      chip.addEventListener("click", () => sendQualifier(chip.dataset.q));
    });
  }

  function closeQualifier() {
    state.qualifierOpen = false;
    $("qualifier").hidden = true;
    $("qualifierBackdrop").hidden = true;
  }

  function sendQualifier(text) {
    const q = (text || "").trim();
    if (!q) return;
    appendMsg("user", q);
    $("qualifierInput").value = "";
    setTimeout(() => appendMsg("bot", replyFor(q)), 350);
  }

  function initQualifier() {
    $("qualifierToggle").addEventListener("click", () => {
      if (state.qualifierOpen) closeQualifier();
      else openQualifier(state.selectedLeadId);
    });
    $("qualifierClose").addEventListener("click", closeQualifier);
    $("qualifierBackdrop").addEventListener("click", closeQualifier);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && state.qualifierOpen) closeQualifier();
    });
    $("qualifierForm").addEventListener("submit", (e) => {
      e.preventDefault();
      sendQualifier($("qualifierInput").value);
    });
  }

  function renderAll() {
    renderHero();
    renderSitePlan();
    renderMatch();
    renderLiveCall();
    renderVisits();
  }

  function boot() {
    if (!window.RE_DATA) {
      setTimeout(boot, 30);
      return;
    }
    initTheme();
    initTabs();
    const clusters = D().interestClusters[state.projectId] || [];
    const hottest = [...clusters].sort((a, b) => b.interestCount - a.interestCount)[0];
    state.clusterId = hottest?.id || null;
    initLiveCall();
    initQualifier();
    renderAll();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
