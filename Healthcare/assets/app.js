/* GenAIForge Healthcare — Patient Access Command Center */
(function () {
  "use strict";

  const D = () => window.HEALTHCARE_DATA;

  const state = {
    clinicId: "mumbai",
    protocolId: "respiratory",
    selectedSlotId: null,
    assistOpen: false,
    escalations: [],
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

  function clinic() {
    return D().clinics.find((c) => c.id === state.clinicId);
  }

  function slots() {
    return D().slots[state.clinicId] || [];
  }

  /* Theme */
  function isDark() {
    return document.documentElement.classList.contains("gf-theme-dark");
  }

  function applyTheme(mode) {
    const root = document.documentElement;
    root.classList.remove("gf-theme-light", "gf-theme-dark");
    root.classList.add(mode === "dark" ? "gf-theme-dark" : "gf-theme-light");
    localStorage.setItem("gf-theme", mode === "dark" ? "dark" : "light");
    const meta = $("themeColorMeta");
    if (meta) meta.content = mode === "dark" ? "#0e1620" : "#f5f8fb";
  }

  function initTheme() {
    applyTheme(isDark() ? "dark" : "light");
    $("themeToggle").addEventListener("click", () => applyTheme(isDark() ? "light" : "dark"));
  }

  /* Clinics */
  function initTabs() {
    const nav = $("clinicTabs");
    nav.innerHTML = D()
      .clinics.map(
        (c) =>
          `<button type="button" class="clinic-tab ${c.id === state.clinicId ? "active" : ""}" data-id="${c.id}">${c.name}</button>`
      )
      .join("");
    nav.querySelectorAll(".clinic-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.clinicId = btn.dataset.id;
        state.selectedSlotId = null;
        nav.querySelectorAll(".clinic-tab").forEach((b) => b.classList.toggle("active", b.dataset.id === state.clinicId));
        renderHero();
        renderCalendar();
        renderIntake(null);
      });
    });
  }

  function renderHero() {
    const c = clinic();
    $("heroMedia").style.backgroundImage = `url("${c.heroImage}")`;
    $("heroSite").textContent = c.site;
    $("heroTitle").textContent = c.heroTitle;
    $("heroSub").textContent = c.heroSub;
    $("heroProofs").innerHTML = c.proofs
      .map((p) => `<div class="proof"><strong>${p.value}</strong><span>${p.label}</span></div>`)
      .join("");
    $("dayLabel").textContent = `${D().dayLabel} · ${c.name}`;
  }

  function renderCalendar() {
    const list = slots();
    $("calGrid").innerHTML = list
      .map((s) => {
        const open = !s.patient;
        const active = s.id === state.selectedSlotId ? "active" : "";
        return `
        <button type="button" class="slot ${open ? "open" : ""} ${active}" data-id="${s.id}" role="listitem">
          <div class="slot-time">${s.time}</div>
          <div class="slot-main">
            <strong>${open ? "Open slot" : s.patient}</strong>
            <span>${s.provider} · ${s.reason}</span>
          </div>
          <div class="slot-meta">
            ${open ? "" : `<span class="risk-pill ${s.risk}">${s.risk}</span>`}
            <span class="rem-status">${s.reminder}</span>
          </div>
        </button>`;
      })
      .join("");

    $("calGrid").querySelectorAll(".slot").forEach((btn) => {
      btn.addEventListener("click", () => {
        const s = list.find((x) => x.id === btn.dataset.id);
        state.selectedSlotId = s.id;
        renderCalendar();
        renderIntake(s);
      });
    });
  }

  function renderIntake(slot) {
    const box = $("intakeBody");
    if (!slot || !slot.patient) {
      box.innerHTML = `<p class="intake-empty">${
        slot && !slot.patient ? "Open slot — use Patient Assistant to book." : "Select a booked slot to view assistive intake."
      }</p>`;
      return;
    }
    box.innerHTML = `
      <div class="intake-card">
        <h3>${slot.patient} · ${slot.time}</h3>
        <div class="meta">${slot.provider} · No-show risk: <strong>${slot.risk}</strong> · ${slot.reminder}</div>
        <ul>${(slot.intake || []).map((i) => `<li>${i}</li>`).join("")}</ul>
        <div class="guard-note">Assistive intake only — AI does not diagnose or recommend treatment.</div>
      </div>`;
  }

  /* Protocols */
  function renderProtocols() {
    const list = D().protocols;
    $("protoTabs").innerHTML = list
      .map(
        (p) =>
          `<button type="button" class="proto-tab ${p.id === state.protocolId ? "active" : ""}" data-id="${p.id}">${p.name}</button>`
      )
      .join("");
    $("protoTabs").querySelectorAll(".proto-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.protocolId = btn.dataset.id;
        renderProtocols();
      });
    });
    const p = list.find((x) => x.id === state.protocolId) || list[0];
    $("protoSteps").innerHTML = p.steps.map((s) => `<li>${s}</li>`).join("");
    $("protoRoute").textContent = "Route: " + p.route;
  }

  /* Escalations */
  function renderEscalations() {
    $("escList").innerHTML = state.escalations
      .map(
        (e) => `
      <li class="esc-item ${e.claimed ? "claimed" : ""}" data-id="${e.id}">
        <header>
          <span class="reason">${e.reason}</span>
          <span class="time">${e.time}</span>
        </header>
        <p>${e.excerpt}</p>
        <div class="row">
          <span class="masked">${e.claimed ? e.unmasked || e.masked : e.masked}</span>
          <button type="button" class="btn btn-sm ${e.claimed ? "btn-ghost" : "btn-accent"}" data-claim="${e.id}" ${
          e.claimed ? "disabled" : ""
        }>${e.claimed ? "Claimed" : "Claim"}</button>
        </div>
      </li>`
      )
      .join("");

    $("escList").querySelectorAll("[data-claim]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const e = state.escalations.find((x) => x.id === btn.dataset.claim);
        if (!e || e.claimed) return;
        e.claimed = true;
        e.unmasked = e.masked.replace(/\*/g, "").replace(/\s+/g, " ") + " (demo claim)";
        toast("Escalation claimed — PII revealed to staff (demo)");
        renderEscalations();
      });
    });
  }

  function pushEscalation(partial) {
    const now = new Date();
    const time =
      String(now.getHours()).padStart(2, "0") + ":" + String(now.getMinutes()).padStart(2, "0");
    state.escalations.unshift({
      id: "e" + Date.now(),
      time,
      claimed: false,
      masked: partial.masked || "P*** · Clinic",
      reason: partial.reason,
      excerpt: partial.excerpt,
    });
    renderEscalations();
  }

  /* Theatrical: book + reminder */
  function bookSlot() {
    const open = slots().find((s) => !s.patient);
    if (!open) {
      toast("No open slots in this clinic (demo)");
      return null;
    }
    open.patient = "D*** B***";
    open.reason = "New · GP booked via assistant";
    open.risk = "low";
    open.reminder = "Confirmed";
    open.intake = ["Booked via Patient Assistant", "Channel: WhatsApp + SMS", "No clinical question unanswered"];
    state.selectedSlotId = open.id;
    renderCalendar();
    renderIntake(open);
    toast("GP slot booked on calendar");
    return open;
  }

  function sendHighRiskReminder() {
    const high = slots().find((s) => s.patient && s.risk === "high");
    if (!high) {
      toast("No high-risk slot in this clinic");
      return null;
    }
    high.reminder = "Extra nudge sent";
    if (state.selectedSlotId === high.id) renderIntake(high);
    renderCalendar();
    toast("Extra reminder sent for high-risk slot");
    return high;
  }

  /* Assistant chat */
  function formatMsg(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  function appendMsg(role, text) {
    const box = $("assistMessages");
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.innerHTML = formatMsg(text);
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  function replyFor(q) {
    const lower = q.toLowerCase();

    if (/rash|diagnos|serious|what.*(have|wrong)|is this|treat|prescribe|disease|cancer|infection/i.test(q)) {
      pushEscalation({
        reason: "Clinical question — deferred",
        excerpt: "Patient asked a clinical question. Bot refused diagnosis and escalated.",
        masked: "P*** · " + clinic().name,
      });
      return D().chat.guardrailReply;
    }

    if (/book|appoint|gp today|schedule/i.test(lower)) {
      bookSlot();
      return D().chat.bookReply;
    }

    if (/remind|nudge|no-?show|high.?risk/i.test(lower)) {
      sendHighRiskReminder();
      return D().chat.reminderReply;
    }

    if (/protocol|respir|fever|triage|intake/i.test(lower)) {
      if (/fever|pedia/i.test(lower)) state.protocolId = "pediatric";
      else if (/rout|appoint/i.test(lower)) state.protocolId = "routing";
      else state.protocolId = "respiratory";
      renderProtocols();
      return D().chat.protocolReply;
    }

    return "I can **book**, **send reminders**, or **run protocol intake**. I never diagnose — ask a clinician for medical advice, or say “Is this rash serious?” to see the guardrail.";
  }

  function sendAssist(text) {
    const q = (text || "").trim();
    if (!q) return;
    appendMsg("user", q);
    $("assistInput").value = "";
    setTimeout(() => appendMsg("bot", replyFor(q)), 280);
  }

  function openAssist() {
    state.assistOpen = true;
    $("assist").hidden = false;
    $("assistBackdrop").hidden = false;
  }

  function closeAssist() {
    state.assistOpen = false;
    $("assist").hidden = true;
    $("assistBackdrop").hidden = true;
  }

  function resetAssist() {
    $("assistMessages").innerHTML = "";
    appendMsg("bot", D().chat.greeting);
    $("assistSuggestions").innerHTML = D()
      .chat.suggestions.map((s) => `<button type="button" class="chip-btn" data-q="${s}">${s}</button>`)
      .join("");
    $("assistSuggestions").querySelectorAll(".chip-btn").forEach((chip) => {
      chip.addEventListener("click", () => sendAssist(chip.dataset.q));
    });
  }

  function initAssist() {
    resetAssist();
    $("assistToggle").addEventListener("click", () => {
      if (state.assistOpen) closeAssist();
      else openAssist();
    });
    $("assistClose").addEventListener("click", closeAssist);
    $("assistBackdrop").addEventListener("click", closeAssist);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && state.assistOpen) closeAssist();
    });
    $("assistForm").addEventListener("submit", (e) => {
      e.preventDefault();
      sendAssist($("assistInput").value);
    });
  }

  function initActions() {
    $("watchDemoBtn").addEventListener("click", () => {
      openAssist();
      sendAssist("Book a GP today");
      setTimeout(() => sendAssist("Send reminder for high-risk slot"), 900);
    });
    $("scrollCalBtn").addEventListener("click", () => {
      $("main").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function boot() {
    if (!window.HEALTHCARE_DATA) {
      setTimeout(boot, 30);
      return;
    }
    state.escalations = D().escalations.map((e) => Object.assign({}, e));
    initTheme();
    initTabs();
    renderHero();
    renderCalendar();
    renderIntake(null);
    renderProtocols();
    renderEscalations();
    initAssist();
    initActions();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
