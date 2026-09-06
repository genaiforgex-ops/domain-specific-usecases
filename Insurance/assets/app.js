/* GenAIForge Insurance — Claim Journey Workspace */
(function () {
  "use strict";

  const D = window.INS_DATA;
  const STAGES = D.stages;
  const THEME_KEY = "gf-theme";

  let state = {
    lob: "motor",
    claimId: null,
    stage: "assess",
    docTab: "bundle",
    theme: "dark",
  };

  /* ── DOM refs ── */
  const $ = (sel) => document.querySelector(sel);

  const els = {
    lobSelect: $("#lobSelect"),
    clock: $("#clock"),
    themeToggle: $("#themeToggle"),
    stageRail: $("#stageRailInner"),
    stageProgressFill: $("#stageProgressFill"),
    claimList: $("#claimList"),
    claimCount: $("#claimCount"),
    agentInsight: $("#agentInsight"),
    insightAgent: $("#insightAgent"),
    insightText: $("#insightText"),
    docTabs: $("#docTabs"),
    paperStack: $("#paperStack"),
    extractTitle: $("#extractTitle"),
    extractConfidence: $("#extractConfidence"),
    fieldList: $("#fieldList"),
    agentTimeline: $("#agentTimeline"),
    hitlContext: $("#hitlContext"),
    hitlActions: $("#hitlActions"),
    btnApprove: $("#btnApprove"),
    btnEscalate: $("#btnEscalate"),
    toast: $("#toast"),
  };

  /* ── Helpers ── */
  function fmtCurrency(n) {
    if (n == null) return "—";
    return "₹" + n.toLocaleString("en-IN");
  }

  function confClass(c) {
    if (c >= 0.9) return "conf-high";
    if (c >= 0.75) return "conf-mid";
    return "conf-low";
  }

  function confLabel(c) {
    return Math.round(c * 100) + "%";
  }

  function getClaims() {
    return D.claims[state.lob] || [];
  }

  function getClaim() {
    return getClaims().find((c) => c.id === state.claimId) || null;
  }

  function getDocs() {
    return state.claimId ? D.documents[state.claimId] : null;
  }

  function stageIndex(id) {
    return STAGES.findIndex((s) => s.id === id);
  }

  function getClaimStageIdx(claim) {
    return claim ? stageIndex(claim.stage) : -1;
  }

  function getViewStageIdx() {
    return stageIndex(state.stage);
  }

  function getPrimaryDoc(docs) {
    if (!docs) return null;
    return docs.policy || docs[docs.tabs[0]?.id] || null;
  }

  function showToast(msg) {
    els.toast.textContent = msg;
    els.toast.classList.add("show");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => els.toast.classList.remove("show"), 3200);
  }

  function updateClock() {
    const now = new Date();
    els.clock.textContent = now.toLocaleTimeString("en-IN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
    els.clock.setAttribute("datetime", now.toISOString());
  }

  /* ── Theme ── */
  function applyTheme(theme) {
    state.theme = theme;
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", theme === "light" ? "#f4f0e8" : "#0e141c");
    if (els.themeToggle) {
      const next = theme === "light" ? "dark" : "light";
      els.themeToggle.setAttribute("aria-label", "Switch to " + next + " mode");
    }
  }

  function initTheme() {
    let theme = localStorage.getItem(THEME_KEY);
    if (theme !== "light" && theme !== "dark") {
      theme = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    }
    applyTheme(theme);
    if (els.themeToggle) {
      els.themeToggle.addEventListener("click", () => {
        applyTheme(state.theme === "light" ? "dark" : "light");
      });
    }
  }

  /* ── Stage tabs ── */
  function getStageTabs() {
    const claim = getClaim();
    const docs = getDocs();
    if (!claim || !docs) return [];

    switch (state.stage) {
      case "intake":
        return [
          { id: "bundle", label: "Intake bundle" },
          { id: "channel", label: claim.channel },
        ];
      case "extract":
        return docs.tabs;
      case "validate":
        return [
          { id: "policy", label: "Policy match" },
          { id: "coverage", label: "Coverage checks" },
        ];
      case "assess":
        return [
          { id: "damage", label: "Damage estimate" },
          { id: "fraud", label: "Fraud signals" },
        ];
      case "settle":
        return [
          { id: "summary", label: "Settlement summary" },
          { id: "packet", label: "Adjuster packet" },
        ];
      default:
        return docs.tabs;
    }
  }

  function defaultDocTabForStage() {
    const tabs = getStageTabs();
    return tabs.length ? tabs[0].id : "policy";
  }

  /* ── Stage panel builders ── */
  function buildIntakePanel(claim, docs, tab) {
    const policyDoc = getPrimaryDoc(docs);
    const attachmentCount = docs.tabs.length;
    const photoTab = docs.photos || docs[docs.tabs.find((t) => t.label.toLowerCase().includes("photo"))?.id];

    if (tab === "channel") {
      return {
        paperTitle: "Channel transcript · " + claim.channel,
        paperClass: "doc-intake",
        stamp: "Received",
        paperLines: [
          claim.channel.toUpperCase() + " FNOL THREAD",
          "Claim: " + claim.id,
          "Policyholder: " + claim.policyholder,
          "",
          "User: Need to register a claim for " + claim.type.toLowerCase() + ".",
          "User: Loss date " + claim.lossDate + " · " + claim.asset,
          "Agent: Acknowledged. Please share policy and damage photos.",
          "User: Uploading " + attachmentCount + " document(s) now…",
          "",
          "Status: Bundle complete · queued for OCR",
        ],
        extractTitle: "Channel metadata",
        confidence: null,
        confidenceLabel: "Intake only",
        animateBars: false,
        fields: [
          { key: "Channel", value: claim.channel, conf: 1.0 },
          { key: "FNOL time", value: "Received · normalised < 90s", conf: 0.99 },
          { key: "Claim type", value: claim.type, conf: 0.98 },
          { key: "Policyholder", value: claim.policyholder, conf: 0.97 },
          { key: "Asset", value: claim.asset, conf: 0.96 },
          { key: "Attachments", value: attachmentCount + " file group(s) · raw upload", conf: 0.95 },
          { key: "OCR status", value: "Pending — not yet extracted", conf: 0.5 },
        ],
      };
    }

    const lines = [
      "RAW INTAKE BUNDLE",
      "Claim: " + claim.id + " · " + claim.type,
      "Channel: " + claim.channel + " · Loss " + claim.lossDate,
      "",
      "Queued uploads:",
    ];
    docs.tabs.forEach((t, i) => {
      lines.push("  □ " + t.label + " · awaiting OCR");
    });
    if (photoTab && photoTab.paperLines) {
      const photoLine = photoTab.paperLines.find((l) => l.includes("photo"));
      if (photoLine) lines.push("  □ " + photoLine.replace(/^[^·]*·\s*/, ""));
    }
    lines.push("", "Pipeline: Intake → Extract (next)", "Status: Raw · unprocessed scan");

    return {
      paperTitle: "Intake bundle · " + claim.id,
      paperClass: "doc-intake raw-upload",
      stamp: "Raw upload",
      paperLines: lines,
      extractTitle: "Intake metadata",
      confidence: null,
      confidenceLabel: "Pre-extraction",
      animateBars: false,
      fields: [
        { key: "Bundle status", value: "Complete · raw files stored", conf: 0.99 },
        { key: "Channel", value: claim.channel, conf: 1.0 },
        { key: "Documents queued", value: docs.tabs.map((t) => t.label).join(" · "), conf: 0.95 },
        { key: "Policy doc", value: policyDoc ? "Uploaded · OCR pending" : "Not yet attached", conf: 0.7 },
        { key: "Media", value: photoTab ? "Photos attached · not analysed" : "No media", conf: 0.85 },
        { key: "Next step", value: "Extract Agent · OCR pipeline", conf: 0.99 },
      ],
    };
  }

  function buildExtractPanel(claim, docs, tab) {
    const doc = docs[tab] || getPrimaryDoc(docs);
    if (!doc) return null;

    const isActive = claim.stage === "extract";
    const stamp = isActive ? "Scanning…" : "Extracted";

    return {
      paperTitle: doc.title,
      paperClass: (doc.docType ? "doc-" + doc.docType : "") + (isActive ? " ocr-active" : ""),
      stamp: stamp,
      paperLines: doc.paperLines,
      extractTitle: "OCR · " + doc.title,
      confidence: doc.confidence,
      confidenceLabel: confLabel(doc.confidence) + " avg · OCR extraction",
      animateBars: isActive,
      fields: doc.fields.map((f, i) => ({
        ...f,
        conf: isActive ? Math.min(f.conf, 0.55 + i * 0.08) : f.conf,
        animDelay: i * 120,
      })),
    };
  }

  function buildValidatePanel(claim, docs, tab) {
    const policyDoc = docs.policy || getPrimaryDoc(docs);
    if (!policyDoc) return null;

    if (tab === "coverage") {
      const coverField = policyDoc.fields.find((f) => /cover|sum/i.test(f.key));
      return {
        paperTitle: "Coverage verification",
        paperClass: "doc-policy validate-highlight",
        stamp: "Verified",
        paperLines: [
          "COVERAGE CHECK RESULTS",
          "Claim: " + claim.id,
          "Policy: " + (policyDoc.fields[0]?.value || "—"),
          "",
          "✓ Policy active on loss date",
          "✓ Premium payment confirmed",
          "✓ " + (coverField ? coverField.value : "Comprehensive cover") + " applies",
          claim.fraudScore > 50 ? "⚠ Elevated fraud score — manual review" : "✓ No coverage exclusions triggered",
          "",
          "Decision: " + (claim.fraudScore > 50 ? "Hold · escalate" : "Proceed to assess"),
        ],
        extractTitle: "Coverage checks",
        confidence: 0.94,
        confidenceLabel: "94% rule match confidence",
        animateBars: false,
        fields: [
          { key: "Policy status", value: "Active · premium paid", conf: 0.99 },
          { key: "Loss date cover", value: "Within policy period", conf: 0.98 },
          { key: "Cover type", value: coverField ? coverField.value : "Comprehensive", conf: 0.97 },
          { key: "Exclusions", value: claim.fraudScore > 50 ? "Fraud hold triggered" : "None matched", conf: 0.93 },
          { key: "NCB / bonus", value: claim.fraudScore > 30 ? "Under review" : "Verified · no lapse", conf: 0.91 },
          { key: "STP eligibility", value: claim.aiRecommendation === "auto_settle" ? "Eligible" : "Manual review required", conf: 0.88 },
        ],
      };
    }

    return {
      paperTitle: "Policy match · " + claim.id,
      paperClass: "doc-policy validate-highlight",
      stamp: "Matched",
      paperLines: policyDoc.paperLines.map((line) => {
        if (/policy no|insured|vehicle|cover|period/i.test(line)) return "▸ " + line;
        return line;
      }),
      extractTitle: "Policy match checks",
      confidence: 0.96,
      confidenceLabel: "96% policy match confidence",
      animateBars: false,
      fields: [
        { key: "Policy ↔ claim", value: "Policyholder matches FNOL", conf: 0.99 },
        { key: "Asset match", value: claim.asset.split("·")[0].trim() + " verified", conf: 0.97 },
        { key: "Premium status", value: "Paid · no lapse", conf: 0.98 },
        { key: "Waiting period", value: claim.fraudScore > 50 ? "⚠ Policy only 11 days old" : "Clear", conf: 0.92 },
        { key: "Prior claims", value: claim.fraudScore > 30 ? "Frequency flagged" : "Within normal band", conf: 0.89 },
        { key: "Fraud score", value: claim.fraudScore + "/100", conf: claim.fraudScore > 50 ? 0.78 : 0.94 },
      ],
    };
  }

  function buildAssessPanel(claim, docs, tab) {
    const photoDoc = docs.photos || docs[docs.tabs.find((t) => /photo|bill|summary|fire/i.test(t.label))?.id];

    if (tab === "fraud") {
      const risk = claim.fraudScore >= 70 ? "High" : claim.fraudScore >= 40 ? "Elevated" : "Low";
      return {
        paperTitle: "Fraud signal scan",
        paperClass: "doc-fir assess-fraud",
        stamp: risk + " risk",
        paperLines: [
          "FRAUD & ANOMALY SCAN",
          "Claim: " + claim.id,
          "Composite score: " + claim.fraudScore + "/100 · " + risk + " risk",
          "",
          claim.fraudScore >= 70 ? "⚠ SIU routing recommended" : claim.fraudScore >= 40 ? "⚠ Manual review suggested" : "✓ Within auto-settle fraud band",
          claim.fraudScore >= 50 ? "⚠ Policy age / timing anomaly" : "✓ No timing anomalies",
          claim.fraudScore >= 35 ? "⚠ Prior claim frequency flagged" : "✓ Claim frequency normal",
          "",
          "Recommendation: " + (claim.aiRecommendation === "escalate" ? "Escalate" : "Proceed STP"),
        ],
        extractTitle: "Fraud signals",
        confidence: 0.87,
        confidenceLabel: "87% model confidence",
        animateBars: false,
        fields: [
          { key: "Composite score", value: claim.fraudScore + "/100 · " + risk, conf: 0.91 },
          { key: "Policy timing", value: claim.fraudScore > 50 ? "Recent inception flagged" : "Normal", conf: 0.88 },
          { key: "Document integrity", value: claim.fraudScore > 60 ? "Timestamp mismatch detected" : "Clean", conf: 0.85 },
          { key: "Claim frequency", value: claim.fraudScore > 30 ? "Above peer baseline" : "Within baseline", conf: 0.86 },
          { key: "Network signals", value: claim.fraudScore > 70 ? "Duplicate VIN inquiry" : "None", conf: 0.82 },
          { key: "Route", value: claim.adjusterRoute || (claim.aiRecommendation === "escalate" ? "SIU review" : "STP path"), conf: 0.9 },
        ],
      };
    }

    const estimate = claim.settlementAmount || claim.estimatedLoss;
    const photoLines = photoDoc ? photoDoc.paperLines.slice(0, 6) : ["Damage assessment pending"];

    return {
      paperTitle: "Damage assessment · " + claim.id,
      paperClass: "doc-photo assess-damage",
      stamp: "Estimated",
      paperLines: [
        "AI DAMAGE ASSESSMENT",
        "Claim: " + claim.id + " · " + claim.type,
        "Estimated loss: " + fmtCurrency(estimate),
        claim.settlementAmount ? "After deductible: " + fmtCurrency(claim.settlementAmount) : "",
        "",
        ...photoLines,
        "",
        "STP band: " + (claim.aiRecommendation === "auto_settle" ? "Within threshold ✓" : "Exceeds cap · adjuster"),
      ].filter(Boolean),
      extractTitle: "Damage estimate",
      confidence: claim.aiConfidence,
      confidenceLabel: confLabel(claim.aiConfidence) + " assess confidence",
      animateBars: claim.stage === "assess",
      fields: [
        { key: "Gross estimate", value: fmtCurrency(claim.estimatedLoss), conf: 0.9 },
        { key: "After deductible", value: fmtCurrency(claim.settlementAmount || claim.estimatedLoss), conf: 0.88 },
        { key: "Repair band", value: photoDoc?.fields?.find((f) => /repair|band|bill/i.test(f.key))?.value || "AI-derived from photos", conf: 0.86 },
        { key: "STP threshold", value: claim.aiRecommendation === "auto_settle" ? "Within ₹50k band" : "Exceeds STP cap", conf: 0.91 },
        { key: "Liability", value: claim.type.includes("Multi") ? "Split uncertain · adjuster" : "Single-party · clear", conf: 0.84 },
        { key: "AI recommendation", value: claim.aiRecommendation === "auto_settle" ? "Auto-settle" : "Escalate", conf: claim.aiConfidence },
      ],
    };
  }

  function buildSettlePanel(claim, docs, tab) {
    const amount = claim.settlementAmount || claim.estimatedLoss;
    const isSettled = claim.status === "auto_settled";
    const isRouted = claim.status === "routed_adjuster" || claim.status === "fraud_hold";

    if (tab === "packet") {
      return {
        paperTitle: "Adjuster packet · " + claim.id,
        paperClass: "doc-fir settle-packet",
        stamp: isRouted ? "Routed" : isSettled ? "Closed" : "Ready",
        paperLines: [
          "ADJUSTER HANDOFF PACKET",
          "Claim: " + claim.id + " · " + claim.type,
          "Policyholder: " + claim.policyholder,
          "",
          "Summary: " + claim.aiSummary,
          "Route: " + (claim.adjusterRoute || "Pending assignment"),
          "",
          "Attachments: policy · photos · timeline · AI rationale",
          "Human action: " + (isSettled ? "Approved settle" : isRouted ? "Escalated" : "Awaiting decision"),
        ],
        extractTitle: "Routing & audit",
        confidence: claim.aiConfidence,
        confidenceLabel: "Audit trail complete",
        animateBars: false,
        fields: [
          { key: "Assigned to", value: claim.adjusterRoute || "Queue · pending", conf: 0.95 },
          { key: "Priority", value: claim.severity === "critical" ? "Critical" : claim.severity === "high" ? "High" : "Standard", conf: 0.98 },
          { key: "Fraud score", value: claim.fraudScore + "/100", conf: 0.94 },
          { key: "AI rationale", value: claim.aiSummary.slice(0, 80) + "…", conf: claim.aiConfidence },
          { key: "Timeline events", value: (D.timelines[claim.id]?.length || 0) + " agent actions logged", conf: 1.0 },
          { key: "Status", value: isSettled ? "Settled" : isRouted ? "Routed" : "Pending HITL", conf: 0.99 },
        ],
      };
    }

    return {
      paperTitle: "Settlement summary · " + claim.id,
      paperClass: "doc-policy settle-summary",
      stamp: isSettled ? "Settled" : "Proposed",
      paperLines: [
        "SETTLEMENT SUMMARY",
        "Claim: " + claim.id,
        "Policyholder: " + claim.policyholder,
        "Loss: " + claim.type + " · " + claim.lossDate,
        "",
        isSettled ? "Status: SETTLED ✓" : isRouted ? "Status: ROUTED TO ADJUSTER" : "Status: AWAITING APPROVAL",
        "Amount: " + fmtCurrency(amount),
        "AI confidence: " + confLabel(claim.aiConfidence),
        "",
        claim.aiSummary,
      ],
      extractTitle: "Settlement line items",
      confidence: claim.aiConfidence,
      confidenceLabel: confLabel(claim.aiConfidence) + " settlement confidence",
      animateBars: false,
      fields: [
        { key: "Recommended action", value: claim.aiRecommendation === "auto_settle" ? "Auto-settle" : "Escalate", conf: claim.aiConfidence },
        { key: "Gross loss", value: fmtCurrency(claim.estimatedLoss), conf: 0.92 },
        { key: "Settlement amount", value: fmtCurrency(amount), conf: claim.aiConfidence },
        { key: "Payment rail", value: isSettled ? "NEFT · disbursed" : "Pending approval", conf: 0.96 },
        { key: "Audit ref", value: claim.id + "-AUD-" + claim.lossDate.replace(/-/g, ""), conf: 0.99 },
        { key: "Decision", value: isSettled ? "Human approved" : isRouted ? "Escalated" : "Awaiting HITL", conf: 0.98 },
      ],
    };
  }

  function getStagePanel() {
    const claim = getClaim();
    const docs = getDocs();
    if (!claim || !docs) return null;

    switch (state.stage) {
      case "intake":
        return buildIntakePanel(claim, docs, state.docTab);
      case "extract":
        return buildExtractPanel(claim, docs, state.docTab);
      case "validate":
        return buildValidatePanel(claim, docs, state.docTab);
      case "assess":
        return buildAssessPanel(claim, docs, state.docTab);
      case "settle":
        return buildSettlePanel(claim, docs, state.docTab);
      default:
        return buildExtractPanel(claim, docs, state.docTab);
    }
  }

  /* ── Stage rail ── */
  function renderStageRail() {
    const claim = getClaim();
    const claimStageIdx = claim ? getClaimStageIdx(claim) : getViewStageIdx();
    const viewIdx = getViewStageIdx();
    const progressPct = claim ? ((claimStageIdx + 1) / STAGES.length) * 100 : 0;

    if (els.stageProgressFill) {
      els.stageProgressFill.style.width = progressPct + "%";
    }

    els.stageRail.innerHTML = STAGES.map((s, i) => {
      const sIdx = stageIndex(s.id);
      let cls = "stage-step";
      if (s.id === state.stage) cls += " active";
      if (claim && sIdx <= claimStageIdx) cls += " done";
      if (claim && sIdx === claimStageIdx && s.id !== state.stage) cls += " current-claim";

      const arrow = i < STAGES.length - 1 ? '<span class="stage-arrow" aria-hidden="true">→</span>' : "";
      return `
        <button type="button" class="${cls}" data-stage="${s.id}" aria-current="${s.id === state.stage ? "step" : "false"}">
          <span class="stage-num">${i + 1}</span>
          <span class="stage-label-block">
            <span class="stage-label">${s.label}</span>
            <span class="stage-hint">${s.hint || ""}</span>
          </span>
        </button>
        ${arrow}
      `;
    }).join("");

    els.stageRail.querySelectorAll(".stage-step").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.stage = btn.dataset.stage;
        state.docTab = defaultDocTabForStage();
        renderStageRail();
        renderDocTabs();
        renderPaper();
        renderFields();
        renderTimeline();
        renderInsight();
      });
    });
  }

  /* ── Claim picker ── */
  function renderClaimList() {
    const claims = getClaims();
    els.claimCount.textContent = claims.length;

    els.claimList.innerHTML = claims
      .map((c) => {
        const sel = c.id === state.claimId ? " selected" : "";
        const stageLabel = STAGES.find((s) => s.id === c.stage)?.label || c.stage;
        return `
          <li>
            <button type="button" class="claim-item${sel}" data-id="${c.id}" role="option" aria-selected="${!!sel}">
              <div class="claim-item-id">${c.id}</div>
              <div class="claim-item-type">${c.type}</div>
              <div class="claim-item-meta">
                <span class="severity-dot severity-${c.severity}"></span>
                <span class="claim-item-channel">${c.channel} · ${stageLabel}</span>
              </div>
            </button>
          </li>
        `;
      })
      .join("");

    els.claimList.querySelectorAll(".claim-item").forEach((btn) => {
      btn.addEventListener("click", () => selectClaim(btn.dataset.id));
    });
  }

  function selectClaim(id) {
    state.claimId = id;
    const claim = getClaim();
    if (claim) {
      state.stage = claim.stage;
      state.docTab = defaultDocTabForStage();
    }
    renderAll();
  }

  /* ── Agent insight ── */
  function renderInsight() {
    const claim = getClaim();
    if (!claim) {
      els.agentInsight.hidden = true;
      return;
    }

    const stageMeta = STAGES.find((s) => s.id === state.stage);
    const stageInsight = {
      intake: { agent: "Intake Agent", text: "Raw FNOL received via " + claim.channel + ". Documents queued — OCR not yet started." },
      extract: { agent: "Extract Agent", text: "OCR pipeline pulling fields from policy and media. Confidence bars update in real time." },
      validate: { agent: "Validate Agent", text: "Policy match and coverage checks against " + claim.id + ". Fraud score " + claim.fraudScore + "/100." },
      assess: { agent: "Assess Agent", text: claim.insight?.text || "Damage estimate and fraud signals under review." },
      settle: { agent: claim.status === "auto_settled" ? "Settle Agent" : "Route Agent", text: claim.aiSummary },
    };

    const insight = stageInsight[state.stage] || claim.insight;
    if (!insight) {
      els.agentInsight.hidden = true;
      return;
    }

    els.agentInsight.hidden = false;
    els.insightAgent.textContent = insight.agent + " · " + (stageMeta?.label || state.stage);
    els.insightText.textContent = insight.text;
  }

  /* ── Documents ── */
  function renderDocTabs() {
    const claim = getClaim();
    if (!claim) {
      els.docTabs.innerHTML = "";
      return;
    }

    const tabs = getStageTabs();
    els.docTabs.innerHTML = tabs
      .map((t) => {
        const active = t.id === state.docTab ? " active" : "";
        return `<button type="button" class="doc-tab${active}" data-tab="${t.id}" role="tab">${t.label}</button>`;
      })
      .join("");

    els.docTabs.querySelectorAll(".doc-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.docTab = btn.dataset.tab;
        renderDocTabs();
        renderPaper();
        renderFields();
      });
    });
  }

  function renderPaper() {
    const claim = getClaim();
    if (!claim) {
      els.paperStack.innerHTML = '<p class="paper-empty">Select a claim to view source documents</p>';
      return;
    }

    const panel = getStagePanel();
    if (!panel) {
      els.paperStack.innerHTML = '<p class="paper-empty">No document for this stage</p>';
      return;
    }

    const lines = panel.paperLines
      .map((line) => {
        const warn = line.startsWith("⚠") ? " warn" : "";
        const ok = line.startsWith("✓") || line.startsWith("▸") ? " ok" : "";
        return line ? `<div class="paper-line${warn}${ok}">${line}</div>` : "<div class='paper-line'>&nbsp;</div>";
      })
      .join("");

    els.paperStack.innerHTML = `
      <div class="paper-card${panel.paperClass ? " " + panel.paperClass : ""}${panel.locked ? " paper-locked" : ""}">
        <div class="stage-badge stage-badge-${state.stage}">${STAGES.find((s) => s.id === state.stage)?.label || state.stage}</div>
        <h4 class="paper-title">${panel.paperTitle}</h4>
        ${lines}
        <div class="paper-stamp">${panel.stamp}</div>
      </div>
    `;
  }

  function renderFields() {
    const claim = getClaim();
    if (!claim) {
      els.extractTitle.textContent = "Extracted fields";
      els.extractConfidence.textContent = "";
      els.fieldList.innerHTML = '<p class="field-empty">Select a claim to view extracted fields</p>';
      return;
    }

    const panel = getStagePanel();
    if (!panel) {
      els.fieldList.innerHTML = '<p class="field-empty">No fields for this stage</p>';
      return;
    }

    els.extractTitle.textContent = panel.extractTitle;
    els.extractConfidence.textContent = panel.confidenceLabel || "";

    const animateClass = panel.animateBars ? " animate-bars" : "";
    els.fieldList.innerHTML = panel.fields
      .map((f) => {
        const warn = String(f.key).startsWith("⚠") ? " warn" : "";
        const delay = f.animDelay != null ? ` style="--bar-delay:${f.animDelay}ms"` : "";
        return `
          <div class="field-row${warn}${animateClass}"${delay}>
            <span class="field-key">${f.key}</span>
            <span class="field-value">${f.value}</span>
            <span class="field-conf-wrap">
              <span class="conf-bar" aria-hidden="true"><span class="conf-bar-fill ${confClass(f.conf)}" style="--conf:${Math.round(f.conf * 100)}%"></span></span>
              <span class="field-conf ${confClass(f.conf)}">${confLabel(f.conf)}</span>
            </span>
          </div>
        `;
      })
      .join("");
  }

  /* ── Timeline ── */
  function renderTimeline() {
    const claim = getClaim();
    let items = claim && D.timelines[claim.id] ? D.timelines[claim.id] : D.defaultTimeline;

    els.agentTimeline.innerHTML = items
      .map((item) => {
        const filtered = item.stage !== state.stage ? " filtered-out" : "";
        return `
          <li class="timeline-item ${item.status}${filtered}" data-stage="${item.stage}">
            <span class="timeline-dot"></span>
            <div class="timeline-body">
              <div class="timeline-agent">${item.agent}</div>
              <div class="timeline-action">${item.action}</div>
              <div class="timeline-time">${item.time}</div>
            </div>
          </li>
        `;
      })
      .join("");
  }

  /* ── HITL bar ── */
  function renderHitl() {
    const claim = getClaim();
    if (!claim) {
      els.hitlContext.innerHTML = '<span class="hitl-empty">Select a claim to review AI recommendation</span>';
      els.hitlActions.hidden = true;
      return;
    }

    const isSettled = claim.status === "auto_settled";
    const isRouted = claim.status === "routed_adjuster" || claim.status === "fraud_hold";
    const recClass = claim.aiRecommendation === "auto_settle" ? "rec-settle" : "rec-escalate";
    const recLabel = claim.aiRecommendation === "auto_settle" ? "Auto-settle" : "Escalate";

    let amountStr = "";
    if (claim.settlementAmount) {
      amountStr = " · " + fmtCurrency(claim.settlementAmount);
    } else if (claim.estimatedLoss) {
      amountStr = " · est. " + fmtCurrency(claim.estimatedLoss);
    }

    els.hitlContext.innerHTML = `
      <div class="hitl-summary">
        <span class="hitl-claim-id">${claim.id} · ${claim.type}</span>
        <span class="hitl-recommendation">
          AI recommends <span class="${recClass}">${recLabel}</span>${amountStr}
        </span>
        <span class="hitl-confidence">Confidence ${confLabel(claim.aiConfidence)} · ${claim.aiSummary}</span>
      </div>
    `;

    els.hitlActions.hidden = false;

    if (isSettled) {
      els.btnApprove.textContent = "Settled ✓";
      els.btnApprove.disabled = true;
      els.btnEscalate.disabled = true;
    } else if (isRouted) {
      els.btnApprove.disabled = true;
      els.btnEscalate.textContent = claim.adjusterRoute ? "Routed · " + claim.adjusterRoute : "Routed ✓";
      els.btnEscalate.disabled = true;
    } else {
      els.btnApprove.textContent = "Approve settle";
      els.btnApprove.disabled = claim.aiRecommendation !== "auto_settle";
      els.btnEscalate.textContent = "Escalate to adjuster";
      els.btnEscalate.disabled = false;
    }
  }

  function handleApprove() {
    const claim = getClaim();
    if (!claim || claim.aiRecommendation !== "auto_settle") return;

    claim.status = "auto_settled";
    claim.stage = "settle";
    state.stage = "settle";
    state.docTab = defaultDocTabForStage();

    const amount = claim.settlementAmount || claim.estimatedLoss;
    if (D.timelines[claim.id]) {
      D.timelines[claim.id].push({
        agent: "Settle Agent",
        action: "Human approved · settled " + fmtCurrency(amount) + " · audit logged",
        time: "just now",
        stage: "settle",
        status: "done",
      });
    }

    showToast(claim.id + " settled " + fmtCurrency(amount) + " — audit trail logged");
    renderAll();
  }

  function handleEscalate() {
    const claim = getClaim();
    if (!claim) return;

    claim.status = "routed_adjuster";
    claim.stage = "settle";
    state.stage = "settle";
    state.docTab = defaultDocTabForStage();

    const route = claim.adjusterRoute || "Senior Adjuster · Queue";
    claim.adjusterRoute = route;

    if (D.timelines[claim.id]) {
      D.timelines[claim.id].push({
        agent: "Route Agent",
        action: "Human escalated → " + route + " · summary attached",
        time: "just now",
        stage: "settle",
        status: "done",
      });
    }

    showToast(claim.id + " escalated to " + route);
    renderAll();
  }

  /* ── LOB ── */
  function initLob() {
    els.lobSelect.innerHTML = D.linesOfBusiness
      .map((l) => `<option value="${l.id}">${l.name}</option>`)
      .join("");

    els.lobSelect.value = state.lob;
    els.lobSelect.addEventListener("change", () => {
      state.lob = els.lobSelect.value;
      const claims = getClaims();
      state.claimId = claims.length ? claims[0].id : null;
      if (state.claimId) {
        const c = getClaim();
        state.stage = c ? c.stage : "intake";
        state.docTab = defaultDocTabForStage();
      }
      renderAll();
    });
  }

  /* ── Render all ── */
  function renderAll() {
    renderStageRail();
    renderClaimList();
    renderInsight();
    renderDocTabs();
    renderPaper();
    renderFields();
    renderTimeline();
    renderHitl();
  }

  /* ── Init ── */
  function init() {
    initTheme();
    initLob();
    const claims = getClaims();
    if (claims.length) {
      state.claimId = claims[0].id;
      state.stage = claims[0].stage;
      state.docTab = defaultDocTabForStage();
    }

    els.btnApprove.addEventListener("click", handleApprove);
    els.btnEscalate.addEventListener("click", handleEscalate);

    updateClock();
    setInterval(updateClock, 1000);

    renderAll();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
