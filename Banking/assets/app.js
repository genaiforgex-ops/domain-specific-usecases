/* GenAIForge Banking — BFSI Voice Command Center */
(function () {
  "use strict";

  const D = () => window.BANK_DATA;

  const state = {
    campaignId: "collections",
    regionId: "west",
    activeCallId: null,
    step: -1,
    timerSec: 0,
    timerId: null,
    outcomes: [],
    auditHash: "—",
  };

  function $(id) {
    return document.getElementById(id);
  }

  function toast(msg) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove("show"), 2600);
  }

  function campaign() {
    return D().campaigns.find((c) => c.id === state.campaignId);
  }

  function roi() {
    return D().roi[state.campaignId][state.regionId];
  }

  function queue() {
    return D().queue[state.campaignId] || [];
  }

  function activeCall() {
    return queue().find((c) => c.id === state.activeCallId) || null;
  }

  /* Theme */
  function isLight() {
    return document.documentElement.classList.contains("gf-theme-light");
  }

  function applyTheme(mode) {
    const root = document.documentElement;
    root.classList.remove("gf-theme-light", "gf-theme-dark");
    root.classList.add(mode === "light" ? "gf-theme-light" : "gf-theme-dark");
    localStorage.setItem("gf-theme", mode === "light" ? "light" : "dark");
    const meta = $("themeColorMeta");
    if (meta) meta.content = mode === "light" ? "#f5f7fa" : "#070b12";
  }

  function initTheme() {
    applyTheme(isLight() ? "light" : "dark");
    $("themeToggle").addEventListener("click", () => applyTheme(isLight() ? "dark" : "light"));
  }

  /* Selects */
  function initSelects() {
    $("campaignSelect").innerHTML = D()
      .campaigns.map((c) => `<option value="${c.id}">${c.short}</option>`)
      .join("");
    $("regionSelect").innerHTML = D()
      .regions.map((r) => `<option value="${r.id}">${r.name}</option>`)
      .join("");
    $("campaignSelect").value = state.campaignId;
    $("regionSelect").value = state.regionId;

    $("campaignSelect").addEventListener("change", () => {
      state.campaignId = $("campaignSelect").value;
      endCall(true);
      renderAll();
    });
    $("regionSelect").addEventListener("change", () => {
      state.regionId = $("regionSelect").value;
      renderHero();
      renderIntel();
    });
  }

  function renderHero() {
    const c = campaign();
    const r = roi();
    $("heroCampaign").textContent = c.name;
    $("proofSaved").textContent = r.costSavedToday;
    $("proofCalls").textContent = String(r.callsToday);
    $("proofAudit").textContent = r.auditedPct + "%";
    $("heroCost").textContent = `AI ${r.costPerCallAi} / call vs human ${r.costPerCallHuman} — illustrative`;
    $("langStrip").innerHTML = D()
      .languages.map((l) => `<span class="lang-chip">${l}</span>`)
      .join("");
  }

  function renderIntel() {
    const funnel = D().dpdFunnel[state.campaignId] || [];
    const max = Math.max(...funnel.map((f) => f.volume), 1);
    const r = roi();
    $("intelMeta").textContent = r.recoveryToday && r.recoveryToday !== "—"
      ? `Recovery today ${r.recoveryToday} · QA ${r.quality}%`
      : `QA ${r.quality}%${r.meetingsBooked != null ? ` · Meetings ${r.meetingsBooked}` : ""}`;

    $("dpdFunnel").innerHTML = funnel
      .map(
        (f) => `
      <div class="funnel-card">
        <div class="funnel-label">${f.label}</div>
        <div class="funnel-vol">${f.volume.toLocaleString("en-IN")}</div>
        <div class="funnel-bar"><i style="width:${Math.round((f.volume / max) * 100)}%"></i></div>
        <div class="funnel-meta">${f.curePct}% cure · ${f.playbook}</div>
      </div>`
      )
      .join("");

    const trend = D().connectTrend;
    const tMax = Math.max(...trend);
    $("connectSpark").innerHTML = trend
      .map((v) => `<span style="height:${Math.round((v / tMax) * 100)}%"></span>`)
      .join("");
    $("connectRate").textContent = `${r.connectRate}% connect`;
  }

  function renderCompliance() {
    const comp = D().compliance;
    $("compWindow").textContent = comp.callingWindow;
    $("compRec").textContent = comp.recording;
    $("compPii").textContent = comp.pii;
    $("compDnd").textContent = comp.dnd;
    $("compHash").textContent = state.auditHash;
  }

  function buildWave(active) {
    const w = $("waveform");
    w.classList.toggle("idle", !active);
    w.innerHTML = Array.from({ length: 36 }, (_, i) => {
      const delay = (i % 9) * 0.07;
      return `<span style="animation-delay:${delay}s;height:${18 + (i % 6) * 12}%"></span>`;
    }).join("");
  }

  function renderQueue() {
    const items = queue();
    $("dialQueue").innerHTML = items
      .map(
        (c) => `
      <li>
        <button type="button" class="queue-item ${c.id === state.activeCallId ? "active" : ""}" data-id="${c.id}">
          <div class="qn">${c.name}</div>
          <div class="qm">${c.lang} · ${c.intent} · ${c.phone}</div>
          <span class="q-status ${c.status}">${c.status}</span>
        </button>
      </li>`
      )
      .join("");

    $("dialQueue").querySelectorAll(".queue-item").forEach((btn) => {
      btn.addEventListener("click", () => joinCall(btn.dataset.id));
    });

    const waiting = items.filter((c) => c.status !== "done").length;
    $("queueFoot").innerHTML = `
      <div><strong>${waiting}</strong>In queue</div>
      <div><strong>${state.activeCallId ? 1 : 0}</strong>On floor</div>
      <div><strong>${state.outcomes.length}</strong>Outcomes</div>`;
  }

  function render360(call) {
    if (!call) {
      $("card360Body").innerHTML = `
        <div><dt>Product</dt><dd>—</dd></div>
        <div><dt>Outstanding</dt><dd>—</dd></div>
        <div><dt>Bucket</dt><dd>—</dd></div>
        <div><dt>Last pay</dt><dd>—</dd></div>
        <div><dt>Consent</dt><dd>—</dd></div>
        <div><dt>DND</dt><dd>—</dd></div>`;
      return;
    }
    const c = call.customer;
    $("card360Body").innerHTML = `
      <div><dt>Product</dt><dd>${c.product}</dd></div>
      <div><dt>Outstanding</dt><dd>${c.outstanding}</dd></div>
      <div><dt>Bucket</dt><dd>${c.dpd}</dd></div>
      <div><dt>Last pay</dt><dd>${c.lastPay}</dd></div>
      <div><dt>Consent / PAN</dt><dd>${c.consent} · ${c.pan}</dd></div>
      <div><dt>DND</dt><dd>${c.dnd}</dd></div>`;
  }

  function renderDisclaimer() {
    $("disclaimer").textContent = campaign().disclaimer;
  }

  function renderTranscript() {
    const call = activeCall();
    const box = $("transcript");
    if (!call || state.step < 0) {
      box.innerHTML = `<div class="bubble agent"><span class="who">System</span>Press <strong>Start live demo call</strong> or pick a queue item.</div>`;
      return;
    }
    const steps = call.steps.slice(0, state.step + 1);
    box.innerHTML = steps
      .map(
        (s) => `
      <div class="bubble ${s.speaker}">
        <span class="who">${s.speaker === "agent" ? "Voice agent" : "Customer"}</span>
        ${s.text}
      </div>`
      )
      .join("");
    box.scrollTop = box.scrollHeight;
  }

  function renderOutcomeButtons() {
    const call = activeCall();
    const bar = $("outcomeBar");
    bar.innerHTML = "";
    if (!call || state.step < 0) return;
    const at = (call.outcomesAt && call.outcomesAt[state.step]) || [];
    at.forEach((type) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-accent btn-sm";
      if (type === "paylink") {
        btn.textContent = "Send UPI payment link";
        btn.addEventListener("click", () => fireOutcome("PTP + UPI link sent", "tag"));
      } else if (type === "meeting") {
        btn.textContent = "Book RM meeting";
        btn.addEventListener("click", () => fireOutcome("RM meeting booked", "tag gold"));
      } else if (type === "escalate") {
        btn.textContent = "Escalate hardship → human";
        btn.addEventListener("click", () => escalateHardship(call));
      } else if (type === "audit") {
        btn.textContent = "Seal audit trail";
        btn.addEventListener("click", () => sealAudit());
      }
      bar.appendChild(btn);
    });
  }

  function fireOutcome(label, cls) {
    if (!state.outcomes.includes(label)) state.outcomes.push(label);
    renderTags();
    toast(label + " (demo)");
  }

  function renderTags() {
    $("outcomeTags").innerHTML = state.outcomes
      .map((o) => {
        const cls = o.includes("Hardship") ? "tag warn" : o.includes("meeting") || o.includes("RM") ? "tag gold" : "tag";
        return `<span class="${cls}">${o}</span>`;
      })
      .join("");
  }

  function escalateHardship(call) {
    fireOutcome("Hardship → human handoff", "tag warn");
    const c = call.customer;
    $("handoffCard").hidden = false;
    $("handoffBody").textContent = `${call.name} · ${c.product} · ${c.outstanding} · ${c.dpd}. Full transcript + LMS context packed for human agent. Fair Practices: same-call escalation.`;
  }

  function sealAudit() {
    const hash =
      "0x" +
      Array.from({ length: 10 }, () => Math.floor(Math.random() * 16).toString(16)).join("") +
      "…";
    state.auditHash = hash;
    fireOutcome("Audit sealed", "tag");
    renderCompliance();
  }

  function fmtTimer(sec) {
    const m = String(Math.floor(sec / 60)).padStart(2, "0");
    const s = String(sec % 60).padStart(2, "0");
    return `${m}:${s}`;
  }

  function startTimer() {
    stopTimer();
    state.timerSec = 0;
    $("callTimer").textContent = "00:00";
    state.timerId = setInterval(() => {
      state.timerSec += 1;
      $("callTimer").textContent = fmtTimer(state.timerSec);
    }, 1000);
  }

  function stopTimer() {
    if (state.timerId) clearInterval(state.timerId);
    state.timerId = null;
  }

  function joinCall(id) {
    const call = queue().find((c) => c.id === id);
    if (!call) return;
    state.activeCallId = id;
    state.step = 0;
    state.outcomes = [];
    state.auditHash = "—";
    $("handoffCard").hidden = true;
    $("callerName").textContent = call.name;
    $("callerChips").innerHTML = `
      <span class="meta-chip">${call.intent}</span>
      <span class="meta-chip">${call.lang}</span>
      <span class="meta-chip">${call.phone}</span>`;
    $("stageLabel").textContent = "NOW TALKING";
    $("advanceBtn").disabled = false;
    $("resetCallBtn").disabled = false;
    buildWave(true);
    startTimer();
    render360(call);
    renderDisclaimer();
    renderTranscript();
    renderOutcomeButtons();
    renderTags();
    renderCompliance();
    renderQueue();
    $("liveFloor").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function endCall(silent) {
    stopTimer();
    state.activeCallId = null;
    state.step = -1;
    state.outcomes = [];
    state.auditHash = "—";
    $("callerName").textContent = "Select a call";
    $("callerChips").innerHTML = "";
    $("stageLabel").textContent = "STANDBY";
    $("advanceBtn").disabled = true;
    $("resetCallBtn").disabled = true;
    $("callTimer").textContent = "00:00";
    $("handoffCard").hidden = true;
    buildWave(false);
    render360(null);
    renderTranscript();
    renderOutcomeButtons();
    renderTags();
    renderCompliance();
    renderQueue();
    if (!silent) toast("Call ended");
  }

  function advance() {
    const call = activeCall();
    if (!call) return;
    if (state.step < call.steps.length - 1) {
      state.step += 1;
      renderTranscript();
      renderOutcomeButtons();
      if (state.step === call.steps.length - 1) {
        toast("Conversation complete — seal audit when ready");
      }
    } else {
      toast("End of script — try Seal audit or pick another call");
    }
  }

  function renderAll() {
    renderHero();
    renderIntel();
    renderDisclaimer();
    renderCompliance();
    renderQueue();
    if (!state.activeCallId) {
      buildWave(false);
      renderTranscript();
    }
  }

  function boot() {
    if (!window.BANK_DATA) {
      setTimeout(boot, 30);
      return;
    }
    initTheme();
    initSelects();
    renderAll();

    $("startDemoBtn").addEventListener("click", () => {
      const first = queue().slice().sort((a, b) => a.priority - b.priority)[0];
      if (first) joinCall(first.id);
    });
    $("advanceBtn").addEventListener("click", advance);
    $("resetCallBtn").addEventListener("click", () => {
      if (state.activeCallId) joinCall(state.activeCallId);
    });
    $("handoffClose").addEventListener("click", () => {
      $("handoffCard").hidden = true;
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
