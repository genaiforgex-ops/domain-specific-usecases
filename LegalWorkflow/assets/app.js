/* GenAIForge LegalOS — panel shell */
(function () {
  "use strict";
  const D = () => window.LEGAL_DATA;
  const TITLES = {
    dashboard: ["Dashboard", "Buyer pitch · brief · modules"],
    tasks: ["Task Manager", "Priority filters · claim · complete"],
    matters: ["Matters", "Intake · request types · SLAs"],
    msa: ["MSA Automation", "Timeline · AI review · negotiation memory"],
    legalbot: ["LegalBot", "Modes · streaming answers · citations"],
    compare: ["Comparison", "Hunk navigator · material flags"],
    playbooks: ["Playbooks", "Standard clauses vs deviations"],
    templates: ["Templates", "Approved contract library"],
    obligations: ["Obligations", "Post-signature tracker"],
    radar: ["Radar", "Regulatory · action-required"],
    trust: ["Trust center", "Security · audit sample · packages"],
  };
  const state = {
    panel: "dashboard",
    msaId: "m1",
    mode: "Review",
    hunkId: "h1",
    chat: [],
    prioFilter: "all",
    streaming: false,
    playbookId: "pb1",
    tplId: "tpl2",
  };

  function $(id) {
    return document.getElementById(id);
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function formatBubbleText(text) {
    const parts = String(text || "")
      .split(/\n\n+/)
      .map((p) => p.trim())
      .filter(Boolean);
    if (!parts.length) return "";
    return parts.map((p) => `<p>${esc(p).replace(/\n/g, "<br>")}</p>`).join("");
  }
  function toast(msg) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove("show"), 2800);
  }
  function msa() {
    return D().msas.find((m) => m.id === state.msaId);
  }
  function isLight() {
    return document.documentElement.classList.contains("gf-theme-light");
  }
  function applyTheme(mode) {
    document.documentElement.classList.remove("gf-theme-light", "gf-theme-dark");
    document.documentElement.classList.add(mode === "light" ? "gf-theme-light" : "gf-theme-dark");
    localStorage.setItem("gf-theme", mode === "light" ? "light" : "dark");
    const meta = $("themeColorMeta");
    if (meta) meta.content = mode === "light" ? "#f7f6f3" : "#0c0d10";
  }

  function updateNavBadges() {
    const due = D().tasks.filter((t) => !t.done && (t.group === "Overdue" || t.group === "Today")).length;
    const negotiating = D().msas.filter((m) => m.stageIndex >= 3 && m.stageIndex < 5).length;
    $("navTasks").textContent = String(due);
    $("navMsa").textContent = String(negotiating);
    const nm = $("navMatters");
    if (nm) nm.textContent = String(D().matters.filter((m) => m.status !== "closed").length);
    const nr = $("navRadar");
    if (nr) nr.textContent = String(D().radar.filter((r) => r.severity === "action").length);
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

  function renderDashboard() {
    $("legalHero").innerHTML = `<div class="hero-inner">
      <p class="hero-eyebrow">GenAIForge · LegalOS</p>
      <h2>Playbook-governed legal AI procurement can trust</h2>
      <p>LegalBot cites your positions. MSA keeps negotiation memory. Obligations close post-signature value. Trust Center answers SOC2, inference-only, and audit in the first meeting.</p>
      <div class="hero-proof">
        <div><strong>HITL</strong><span>Per-clause accept/reject</span></div>
        <div><strong>§ cite</strong><span>Source-linked answers</span></div>
        <div><strong>7yr</strong><span>Audit retention (demo)</span></div>
      </div>
      <div class="row-actions" style="padding:0;margin-top:0.85rem">
        <button type="button" class="btn btn-accent" data-goto="legalbot">Open LegalBot</button>
        <button type="button" class="btn btn-ghost" data-goto="trust">Trust center</button>
        <button type="button" class="btn btn-ghost" data-goto="obligations">Obligations</button>
      </div>
    </div>`;
    $("legalHero").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });

    $("dashTiles").innerHTML = D()
      .tiles.map(
        (t) => `<button type="button" class="kpi" data-goto="${t.panel}">
        <strong>${t.value}</strong><span>${t.label}</span>
        <span class="hint">${t.hint} →</span>
      </button>`
      )
      .join("");
    $("dashTiles").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });

    $("briefLine").textContent = D().dailyBrief.summary;
    $("briefActions").innerHTML = D()
      .dailyBrief.actions.map(
        (a) => `<button type="button" class="action-chip" data-goto="${a.panel}">${a.label}</button>`
      )
      .join("");
    $("briefActions").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });

    $("recentActivity").innerHTML = D()
      .recentActivity.map(
        (a) => `<li><time>${a.at}</time><div><strong>${a.actor}</strong> — ${a.text}</div></li>`
      )
      .join("");

    if ($("buyerThemeFeed")) {
      $("buyerThemeFeed").innerHTML = D()
        .buyerThemes.map(
          (t) => `<article class="theme-card">
          <div class="chip-row"><span class="chip chip-muted">${t.source}</span></div>
          <strong>${t.title}</strong>
          <p>${t.takeaway}</p>
          <p class="page-sub"><strong>GenAIForge:</strong> ${t.forgeAction}</p>
        </article>`
        )
        .join("");
    }
  }

  function renderTasks() {
    const groups = ["Overdue", "Today", "This week"];
    const open = D().tasks.filter((t) => !t.done);
    $("taskMeta").textContent = `${open.length} open · filter ${state.prioFilter}`;

    document.querySelectorAll("#taskFilters .filter-chip").forEach((c) => {
      c.classList.toggle("active", c.getAttribute("data-prio") === state.prioFilter);
    });

    let html = "";
    groups.forEach((g) => {
      let items = D().tasks.filter((t) => t.group === g);
      if (state.prioFilter !== "all") items = items.filter((t) => t.priority === state.prioFilter);
      if (!items.length) {
        if (state.prioFilter === "all") return;
        return;
      }
      html += `<div class="task-group"><h3>${g} · ${items.length}</h3>`;
      items.forEach((t) => {
        const overdue = g === "Overdue" && !t.done;
        html += `<div class="task ${t.done ? "done" : ""} ${overdue ? "overdue" : ""}" data-id="${t.id}">
          <div>
            <div class="task-title"><span class="prio ${t.priority.toLowerCase()}">${t.priority}</span>${t.title}</div>
            <div class="task-meta">Due ${t.due}${t.owner ? " · " + t.owner : ""}</div>
          </div>
          <div class="task-actions">
            ${
              t.done
                ? `<span class="btn btn-sm btn-ghost" style="cursor:default">Done</span>`
                : `<button type="button" class="btn btn-sm btn-ghost" data-act="claim">${t.owner ? "Yours" : "Claim"}</button>
                   <button type="button" class="btn btn-sm btn-accent" data-act="complete">Complete</button>`
            }
          </div>
        </div>`;
      });
      html += `</div>`;
    });
    if (!html) html = `<div class="empty">No tasks for this filter. Clear filter or celebrate.</div>`;
    $("taskBoard").innerHTML = html;

    $("taskBoard").querySelectorAll(".task").forEach((row) => {
      row.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          const task = D().tasks.find((t) => t.id === row.getAttribute("data-id"));
          const act = btn.getAttribute("data-act");
          if (act === "claim") {
            task.owner = "You";
            toast("Claimed · " + task.title);
          } else if (act === "complete") {
            task.done = true;
            task.owner = task.owner || "You";
            toast("Completed · " + task.title);
          }
          updateNavBadges();
          renderTasks();
        });
      });
    });
  }

  function renderMsaList() {
    $("msaList").innerHTML = D()
      .msas.map((m) => {
        const stage = D().stages[m.stageIndex];
        return `<li data-id="${m.id}" class="${m.id === state.msaId ? "active" : ""}">
          <div class="t">${m.vendor}</div>
          <div class="s">${m.type} · ${stage} · ${m.value}</div>
          <span class="risk-pill">Risk ${m.risk}</span>
        </li>`;
      })
      .join("");
    $("msaList").querySelectorAll("li").forEach((li) => {
      li.addEventListener("click", () => {
        state.msaId = li.getAttribute("data-id");
        renderMsa();
        renderMsaList();
      });
    });
  }

  function renderMsa() {
    const m = msa();
    $("msaTitle").textContent = m.vendor;
    $("msaSub").textContent = `${m.type} · ${m.value} · Owner ${m.owner}`;
    $("msaTimeline").innerHTML = D()
      .stages.map((s, i) => {
        const cls = i < m.stageIndex ? "done" : i === m.stageIndex ? "active" : "";
        return `<div class="tl-step ${cls}">${s}</div>`;
      })
      .join("");
    $("docBody").textContent = m.excerpt;
    $("riskBadge").textContent = "Risk score " + m.risk + "/100";
    const sugg = (m.suggestions && m.suggestions[m.stageIndex]) || [
      "No stage-gated suggestions for this step",
    ];
    $("suggestions").innerHTML =
      sugg.map((s) => `<li>${s}</li>`).join("") +
      `<div class="hitl-note">HITL: accept/reject each suggestion — never bulk-blind apply (demo).</div>`;
    $("msaMemory").innerHTML =
      `<h4>Negotiation memory</h4>` +
      `<p class="mem-lead">Prior rejections travel with the deal — counsel sees why 3-month cap failed.</p>` +
      (m.memory || [])
        .map((n) => `<div class="memory-item"><strong>${n.by}</strong> · ${n.at}<br/>${n.text}</div>`)
        .join("") || `<div class="empty">No notes yet.</div>`;
    $("advanceMsaBtn").disabled = m.stageIndex >= D().stages.length - 1;
  }

  function renderPlaybooks() {
    const tabs = D()
      .playbooks.map(
        (p) =>
          `<button type="button" class="filter-chip ${p.id === state.playbookId ? "active" : ""}" data-pb="${p.id}">${p.name}</button>`
      )
      .join("");
    const pb = D().playbooks.find((p) => p.id === state.playbookId);
    $("playbookBoard").innerHTML = `<div class="card-head"><div><h2>Playbook management</h2><p>Standard vs deviations</p></div></div>
      <div class="filters" style="padding:0.65rem 1rem 0">${tabs}</div>
      <div class="pb-table pad">
        <div class="pb-head"><span>Clause</span><span>Standard</span><span>Deviation</span><span>Status</span></div>
        ${pb.clauses
          .map(
            (c) => `<div class="pb-row">
            <span>${c.name}</span><span>${c.standard}</span><span>${c.deviation}</span>
            <span class="chip status-${c.status}">${c.status}</span>
          </div>`
          )
          .join("")}
      </div>
      <div class="pad"><button type="button" class="btn btn-accent btn-sm" data-goto="legalbot">Ask LegalBot against playbook</button></div>`;
    $("playbookBoard").querySelectorAll("[data-pb]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.playbookId = btn.getAttribute("data-pb");
        renderPlaybooks();
      });
    });
    $("playbookBoard").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });
  }

  function renderRadar() {
    $("radarList").innerHTML = D()
      .radar.map(
        (n) => `<div class="radar-row ${n.severity}">
        <div>
          <div class="t">${n.title}</div>
          <div class="s">${n.action}</div>
          ${n.source ? `<div class="page-sub" style="margin-top:0.25rem">${n.source} · demo/illustrative</div>` : ""}
        </div>
        <div class="radar-side">
          <span class="chip">${n.severity}</span>
          <span class="page-sub">${n.at}</span>
          <button type="button" class="btn btn-sm btn-ghost" data-goto="playbooks">Update playbook</button>
        </div>
      </div>`
      )
      .join("");
    $("radarList").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });
  }

  function renderTemplates() {
    $("tplList").innerHTML = D()
      .templates.map(
        (t) => `<button type="button" class="tpl-row ${t.id === state.tplId ? "active" : ""}" data-id="${t.id}">
        <div><div class="t">${t.name}</div><div class="s">${t.type} · ${t.version}</div></div>
        <span class="chip ${t.status === "approved" ? "chip-ok" : "chip-muted"}">${t.status}</span>
      </button>`
      )
      .join("");
    $("tplList").querySelectorAll(".tpl-row").forEach((row) => {
      row.addEventListener("click", () => {
        state.tplId = row.getAttribute("data-id");
        renderTemplates();
      });
    });
  }

  function renderObligations() {
    $("oblList").innerHTML = D()
      .obligations.map(
        (o) => `<div class="obl-row">
        <div>
          <div class="t">${o.priority ? `<span class="chip chip-muted">${o.priority}</span> ` : ""}${o.item}</div>
          <div class="s">${o.contract} · Owner ${o.owner} · Due ${o.due}</div>
        </div>
        <span class="chip">${o.status}</span>
      </div>`
      )
      .join("");
  }

  function renderMatters() {
    $("matterList").innerHTML = D()
      .matters.map(
        (m) => `<div class="matter-row ${m.status}">
        <div>
          <div class="t"><span class="chip chip-muted">${m.type}</span> ${m.title}</div>
          <div class="s">${m.requester} · ${m.sla}</div>
        </div>
        <span class="chip">${m.status.replace(/_/g, " ")}</span>
      </div>`
      )
      .join("");
  }

  function renderTrust() {
    const t = D().trust;
    $("trustBoard").innerHTML = `
      <div class="card hero-legal"><div class="hero-inner">
        <p class="hero-eyebrow">Buyer trust center</p>
        <h2>SOC2, inference-only, source-linked AI — demo-labeled</h2>
        <p>${t.retention} · ${t.residency}</p>
        <div class="chip-row" style="margin-top:0.75rem">${t.claims.map((c) => `<span class="chip">${c}</span>`).join("")}</div>
      </div></div>
      <div class="split">
        <div class="card"><div class="card-head"><div><h2>Audit log sample</h2><p>AI decisions + human overrides</p></div>
          <button type="button" class="btn btn-ghost btn-sm" id="exportAuditBtn">Export CSV</button></div>
          <div class="pad">${t.auditSample
            .map(
              (a) => `<div class="audit-row"><time>${a.at}</time><div><strong>${a.actor}</strong> — ${a.action}<div class="s">${a.detail}</div></div></div>`
            )
            .join("")}</div>
        </div>
        <div class="card"><div class="card-head"><div><h2>What you get</h2><p>Pilot / Production</p></div></div>
          <div class="pkg-row pad">${t.packages
            .map(
              (p) => `<article class="pkg"><h4>${p.name}</h4><ul>${p.points.map((x) => `<li>${x}</li>`).join("")}</ul></article>`
            )
            .join("")}</div>
          <div class="pad"><button type="button" class="btn btn-accent" data-goto="legalbot">See LegalBot citations</button></div>
        </div>
      </div>`;
    $("exportAuditBtn").addEventListener("click", () => toast("Audit CSV exported · legal_audit_sample.csv (demo)"));
    $("trustBoard").querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-goto")));
    });
  }

  function renderPanel() {
    updateNavBadges();
    if (state.panel === "dashboard") renderDashboard();
    if (state.panel === "tasks") renderTasks();
    if (state.panel === "msa") {
      renderMsaList();
      renderMsa();
    }
    if (state.panel === "legalbot") renderChat();
    if (state.panel === "compare") renderDiff();
    if (state.panel === "playbooks") renderPlaybooks();
    if (state.panel === "radar") renderRadar();
    if (state.panel === "templates") renderTemplates();
    if (state.panel === "obligations") renderObligations();
    if (state.panel === "matters") renderMatters();
    if (state.panel === "trust") renderTrust();
  }

  function renderChatShell() {
    $("modeChips").innerHTML = D()
      .legalbot.modes.map(
        (m) =>
          `<button type="button" class="mode-chip ${m === state.mode ? "active" : ""}" data-mode="${m}">${m}</button>`
      )
      .join("");
    $("modeChips").querySelectorAll(".mode-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.mode = btn.getAttribute("data-mode");
        state.chat = [
          {
            role: "bot",
            text:
              "LegalBot is in " +
              state.mode +
              " mode.\n\nAsk about a clause, risk position, or draft — answers cite the active playbook.",
          },
        ];
        renderChatMessages();
        renderChatShell();
      });
    });
    $("chatSuggestions").innerHTML = D()
      .legalbot.prompts.map((p, i) => `<button type="button" data-i="${i}">${p.q}</button>`)
      .join("");
    $("chatSuggestions").querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = D().legalbot.prompts[Number(btn.getAttribute("data-i"))];
        askLegalBot(p.q, p.a, p.cite);
      });
    });
  }

  function renderChatMessages() {
    $("chatLog").innerHTML = state.chat
      .map((m) => {
        const isUser = m.role === "user";
        const role = isUser ? "You" : "LegalBot";
        const avatar = isUser ? "YOU" : "LB";
        let body;
        if (m.typing && !m.text) {
          body = `<div class="bubble typing"><span class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></span></div>`;
        } else {
          const cite = m.cite ? `<span class="cite">${esc(m.cite)}</span>` : "";
          body = `<div class="bubble">${formatBubbleText(m.text)}${cite}</div>`;
        }
        return `<article class="msg ${isUser ? "user" : "bot"}">
          <div class="msg-avatar" aria-hidden="true">${avatar}</div>
          <div class="msg-body">
            <div class="msg-meta">${role}${m.typing ? " · drafting" : ""}</div>
            ${body}
          </div>
        </article>`;
      })
      .join("");
    $("chatLog").scrollTop = $("chatLog").scrollHeight;
  }

  function patchStreamingBubble(bot) {
    const log = $("chatLog");
    const last = log && log.querySelector(".msg.bot:last-of-type");
    if (!last) {
      renderChatMessages();
      return;
    }
    const meta = last.querySelector(".msg-meta");
    const bubble = last.querySelector(".bubble");
    if (!bubble) {
      renderChatMessages();
      return;
    }
    if (meta) meta.textContent = bot.typing ? "LegalBot · drafting" : "LegalBot";
    if (bot.typing && !bot.text) {
      bubble.className = "bubble typing";
      bubble.innerHTML =
        '<span class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></span>';
    } else if (bot.typing) {
      bubble.className = "bubble";
      bubble.textContent = bot.text;
    } else {
      const cite = bot.cite ? `<span class="cite">${esc(bot.cite)}</span>` : "";
      bubble.className = "bubble";
      bubble.innerHTML = formatBubbleText(bot.text) + cite;
    }
    log.scrollTop = log.scrollHeight;
  }

  function askLegalBot(question, answer, cite) {
    if (state.streaming) return;
    if (state._streamTimer) {
      clearTimeout(state._streamTimer);
      state._streamTimer = null;
    }
    state.chat.push({ role: "user", text: question });
    state.chat.push({ role: "bot", text: "", typing: true });
    renderChatMessages();
    state.streaming = true;
    const bot = state.chat[state.chat.length - 1];
    const full = answer;
    const step = Math.max(3, Math.ceil(full.length / 28));
    let i = 0;
    const tick = () => {
      i = Math.min(full.length, i + step);
      bot.text = full.slice(0, i);
      if (i >= full.length) {
        bot.text = full;
        bot.typing = false;
        bot.cite = cite;
        state.streaming = false;
        state._streamTimer = null;
        patchStreamingBubble(bot);
        return;
      }
      patchStreamingBubble(bot);
      state._streamTimer = setTimeout(tick, 32);
    };
    state._streamTimer = setTimeout(tick, 180);
  }

  function renderChat() {
    if (!state.chat.length) {
      state.chat.push({
        role: "bot",
        text:
          "LegalBot is in " +
          state.mode +
          " mode.\n\nAsk about a clause, risk position, or draft — answers cite the active playbook.",
      });
    }
    renderChatShell();
    renderChatMessages();
  }

  function renderDiff() {
    const c = D().comparison;
    $("diffMeta").textContent = c.title + " · " + c.hunks.length + " hunks";
    $("diffNav").innerHTML = c.hunks
      .map((h) => {
        const mat = h.material ? "mat" : "";
        return `<button type="button" class="${h.id === state.hunkId ? "active" : ""} ${mat}" data-id="${h.id}">
          ${h.label} ${h.material ? "· M" : ""}
        </button>`;
      })
      .join("");
    $("diffNav").querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.hunkId = btn.getAttribute("data-id");
        renderDiff();
      });
    });

    const hunk = c.hunks.find((h) => h.id === state.hunkId);
    $("diffView").innerHTML =
      hunk.lines.map((l) => `<span class="${l.t}">${l.v}</span>`).join("") +
      `<div class="diff-flag ${hunk.material ? "material" : ""}">${hunk.flag}</div>`;

    $("riskFlags").innerHTML = c.riskFlags
      .map((f, i) => {
        const hunkId = c.hunks[i] ? c.hunks[i].id : state.hunkId;
        return `<div class="risk-flag ${f.severity}" data-hunk="${hunkId}">
          <div class="sev">${f.severity}</div>
          ${f.label}
        </div>`;
      })
      .join("");
    $("riskFlags").querySelectorAll(".risk-flag").forEach((el) => {
      el.addEventListener("click", () => {
        state.hunkId = el.getAttribute("data-hunk");
        renderDiff();
        toast("Jumped to hunk");
      });
    });
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

    $("taskFilters").querySelectorAll(".filter-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        state.prioFilter = chip.getAttribute("data-prio");
        renderTasks();
      });
    });

    $("advanceMsaBtn").addEventListener("click", () => {
      const m = msa();
      if (m.stageIndex < D().stages.length - 1) {
        m.stageIndex += 1;
        m.memory = m.memory || [];
        m.memory.push({
          at: "Just now",
          by: "You",
          text: "Advanced to " + D().stages[m.stageIndex],
        });
        toast("Advanced to " + D().stages[m.stageIndex]);
        updateNavBadges();
        renderMsa();
        renderMsaList();
      }
    });

    $("clearChatBtn").addEventListener("click", () => {
      state.chat = [
        {
          role: "bot",
          text:
            "Thread cleared.\n\nLegalBot is ready in " +
            state.mode +
            " mode — pick a suggestion or type a question.",
        },
      ];
      renderChatMessages();
      toast("Thread cleared");
    });

    $("chatSendBtn").addEventListener("click", () => {
      const q = $("chatInput").value.trim();
      if (!q) return;
      $("chatInput").value = "";
      const known = D().legalbot.prompts.find((p) => p.q.toLowerCase() === q.toLowerCase());
      if (known) askLegalBot(known.q, known.a, known.cite);
      else
        askLegalBot(
          q,
          "Demo response (" +
            state.mode +
            "): I would check your clause library and negotiation memory for “" +
            q +
            "”, then cite the governing playbook section.",
          "Demo · " + state.mode
        );
    });
    $("chatInput").addEventListener("keydown", (e) => {
      if (e.key === "Enter") $("chatSendBtn").click();
    });

    const useTpl = $("useTplBtn");
    if (useTpl) {
      useTpl.addEventListener("click", () => {
        const t = D().templates.find((x) => x.id === state.tplId);
        toast("Template “" + (t ? t.name : "") + "” attached to MSA draft (demo)");
        showPanel("msa");
      });
    }
    const newMatter = $("newMatterBtn");
    if (newMatter) {
      newMatter.addEventListener("click", () => {
        D().matters.unshift({
          id: "mt" + (D().matters.length + 1),
          type: "Advice",
          requester: "You",
          title: "Demo intake · " + new Date().toLocaleTimeString(),
          status: "intake",
          sla: "Due 3d",
        });
        toast("Intake logged");
        updateNavBadges();
        renderMatters();
      });
    }

    showPanel("dashboard");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
