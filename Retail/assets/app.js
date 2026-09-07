/* GenAIForge Retail — Conversational Commerce Studio */
(function () {
  "use strict";

  const D = () => window.RETAIL_DATA;

  const state = {
    storeId: "fashion",
    chatOpen: false,
    filterIds: null,
    filterLabel: "",
    opsOpen: false,
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

  function store() {
    return D().stores.find((s) => s.id === state.storeId);
  }

  function products() {
    return D().products[state.storeId] || [];
  }

  function rupee(n) {
    return "₹" + n.toLocaleString("en-IN");
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
    if (meta) meta.content = mode === "dark" ? "#0c0d10" : "#f6f7f9";
  }

  function initTheme() {
    applyTheme(isDark() ? "dark" : "light");
    $("themeToggle").addEventListener("click", () => applyTheme(isDark() ? "light" : "dark"));
  }

  /* Store tabs */
  function initTabs() {
    const nav = $("storeTabs");
    nav.innerHTML = D()
      .stores.map(
        (s) =>
          `<button type="button" class="store-tab ${s.id === state.storeId ? "active" : ""}" data-id="${s.id}">${s.name.split(" ")[0]}</button>`
      )
      .join("");
    nav.querySelectorAll(".store-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.storeId = btn.dataset.id;
        state.filterIds = null;
        state.filterLabel = "";
        nav.querySelectorAll(".store-tab").forEach((b) => b.classList.toggle("active", b.dataset.id === state.storeId));
        renderHero();
        renderGrid();
        renderOps();
        hideWismo();
      });
    });
  }

  function renderHero() {
    const s = store();
    $("heroMedia").style.backgroundImage = `url("${s.heroImage}")`;
    $("heroEyebrow").textContent = s.name;
    $("heroTitle").textContent = s.heroTitle;
    $("heroSub").textContent = s.heroSub;
    $("heroProof").textContent = s.proof;
    $("gridTitle").textContent = s.gridTitle;
    $("gridSub").textContent = s.gridSub;
    $("heroChips").innerHTML = s.chips
      .map((c) => `<button type="button" class="chip" data-q="${c}">${c}</button>`)
      .join("");
    $("heroChips").querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        openChat();
        sendChatSafe(chip.dataset.q);
      });
    });
  }

  function renderGrid() {
    const list = products();
    const hits = state.filterIds;
    $("clearFilterBtn").hidden = !hits;
    $("productGrid").innerHTML = list
      .map((p) => {
        const dim = hits && !hits.includes(p.id);
        const hit = hits && hits.includes(p.id);
        return `
        <article class="product-card ${dim ? "dim" : ""} ${hit ? "hit" : ""}" data-id="${p.id}" role="listitem">
          <img class="product-photo" src="${p.image}" alt="${p.name}" loading="lazy"
            onerror="this.style.background='linear-gradient(135deg,${p.gradient[0]},${p.gradient[1]})'"/>
          <div class="product-body">
            <div class="product-cat">${p.category}</div>
            <div class="product-name">${p.name}</div>
            <div class="product-price">${rupee(p.price)}</div>
          </div>
        </article>`;
      })
      .join("");

    $("productGrid").querySelectorAll(".product-card").forEach((card) => {
      card.addEventListener("click", () => {
        const p = list.find((x) => x.id === card.dataset.id);
        if (!p) return;
        openChat();
        sendChatSafe("Tell me about " + p.name);
      });
    });
  }

  function renderOps() {
    const o = D().ops[state.storeId];
    $("opsKpis").innerHTML = `
      <div class="ops-kpi"><strong>${o.ticketsDeflected}</strong><span>Tickets deflected</span></div>
      <div class="ops-kpi"><strong>${o.conversionLift}</strong><span>Conversion assist</span></div>
      <div class="ops-kpi"><strong>${o.csat}</strong><span>CSAT</span></div>
      <div class="ops-kpi"><strong>${o.aovInfluenced}</strong><span>AOV influenced</span></div>
      <div class="ops-kpi"><strong>${o.handoffsToday}</strong><span>Handoffs today</span></div>
      <div class="ops-kpi"><strong>${o.avgResponseSec}s</strong><span>Avg first reply</span></div>`;
    $("opsIntents").innerHTML = o.intents
      .map(
        (i) =>
          `<div class="ops-bar"><span>${i.label}</span><div class="ops-bar-track"><i style="width:${i.pct}%"></i></div><em>${i.pct}%</em></div>`
      )
      .join("");
    $("opsChannels").innerHTML = (o.channels || [])
      .map(
        (c) =>
          `<div class="ops-bar"><span>${c.label}</span><div class="ops-bar-track"><i style="width:${c.pct}%"></i></div><em>${c.pct}%</em></div>`
      )
      .join("");
    $("opsRecent").innerHTML = (o.recent || [])
      .map(
        (r) =>
          `<li><time>${r.time}</time><span class="ops-type">${r.type}</span><span class="ops-detail">${r.detail}</span><span class="ops-outcome">${r.outcome}</span></li>`
      )
      .join("");
  }

  /* Filter / co-browse */
  function applyFilter(ids, label) {
    state.filterIds = ids && ids.length ? ids : null;
    state.filterLabel = label || "";
    renderGrid();
  }

  function matchProducts(q) {
    const list = products();
    const lower = q.toLowerCase();
    const budget = /(?:under|below|less than)\s*₹?\s*([\d,]+)/i.exec(q);
    let max = budget ? parseInt(budget[1].replace(/,/g, ""), 10) : null;
    if (!max && /under\s*₹?\s*2,?000|under 2000/i.test(q)) max = 2000;
    if (!max && /under\s*₹?\s*4,?000/i.test(q)) max = 4000;
    if (!max && /under\s*₹?\s*5,?000/i.test(q)) max = 5000;

    const words = lower
      .replace(/show me|something|please|find|looking for|i need|i want/gi, "")
      .split(/[\s,]+/)
      .filter((w) => w.length > 2);

    return list.filter((p) => {
      if (max != null && p.price > max) return false;
      if (!words.length && max != null) return true;
      const hay = (p.name + " " + p.category + " " + p.tags.join(" ")).toLowerCase();
      return words.some((w) => hay.includes(w)) || (max != null && p.price <= max);
    });
  }

  /* WISMO */
  function showWismo(orderId) {
    const order = D().orders[orderId];
    if (!order) return false;
    const steps = D().trackSteps;
    $("wismoRail").hidden = false;
    $("wismoTitle").textContent = `Order ${orderId}`;
    $("wismoMeta").textContent = `${order.items.join(", ")} · ${order.carrier} · ${order.eta}`;
    $("trackSteps").innerHTML = steps
      .map((s, i) => {
        const cls = i < order.step ? "done" : i === order.step ? "active" : "";
        return `<li class="${cls}">${s}</li>`;
      })
      .join("");
    $("wismoRail").scrollIntoView({ behavior: "smooth", block: "nearest" });
    return true;
  }

  function hideWismo() {
    $("wismoRail").hidden = true;
  }

  /* Chat */
  function formatMsg(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  function appendMsg(role, text) {
    const box = $("chatMessages");
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.innerHTML = formatMsg(text);
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
  }

  function appendSkuRow(list) {
    if (!list || !list.length) return;
    const box = $("chatMessages");
    const row = document.createElement("div");
    row.className = "sku-row";
    row.innerHTML = list
      .slice(0, 4)
      .map(
        (p) =>
          `<button type="button" class="sku-chip" data-id="${p.id}"><img src="${p.image}" alt=""/><div><strong>${p.name}</strong><div>${rupee(p.price)}</div></div></button>`
      )
      .join("");
    box.appendChild(row);
    row.querySelectorAll(".sku-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const p = products().find((x) => x.id === chip.dataset.id);
        if (p) sendChatSafe("Tell me about " + p.name);
      });
    });
    box.scrollTop = box.scrollHeight;
  }

  function isHandoff(q) {
    return D().chat.handoffKeywords.some((k) => q.toLowerCase().includes(k));
  }

  function replyFor(q) {
    const orderMatch = q.toUpperCase().match(/\b(SF|NH|TM)-\d+\b/);
    if (orderMatch || /where is my order|track|wismo|delivery/i.test(q)) {
      const id = orderMatch
        ? orderMatch[0]
        : state.storeId === "home"
          ? "NH-551023"
          : state.storeId === "electronics"
            ? "TM-663401"
            : "SF-284719";
      if (showWismo(id)) {
        const o = D().orders[id];
        return {
          text: `**${id}** is **${o.status}**.\n${o.items.join(", ")} · ${o.carrier} · ${o.eta}\nTracking rail updated below the catalog.`,
        };
      }
    }

    if (/return|refund|exchange/i.test(q)) {
      const r = D().returns;
      toast("Return label created (demo)");
      return {
        text: `**Return started** (demo)\n• Window: ${r.window}\n• Condition: ${r.condition}\n• Pickup: ${r.freePickup ? "Free doorstep pickup" : "Drop-off"}\n• Refund: ${r.refund}\nA prepaid label would be emailed — human warehouse still inspects.`,
      };
    }

    if (isHandoff(q)) {
      $("handoffToast").hidden = false;
      $("handoffTitle").textContent =
        state.storeId === "electronics" ? "Connecting a tech specialist" : "Connecting you with a stylist";
      $("handoffMsg").textContent = "High-intent shopper — full transcript + viewed SKUs packed for the human.";
      return {
        text: "**Handoff requested.** A human specialist will pick up with this chat context. I stay on the thread until they join.",
      };
    }

    if (/tell me about /i.test(q)) {
      const name = q.replace(/tell me about /i, "").trim();
      const p = products().find((x) => x.name.toLowerCase() === name.toLowerCase());
      if (p) {
        applyFilter([p.id], p.name);
        return {
          text: `**${p.name}** — ${rupee(p.price)} · ${p.category}.\nIn stock. 30-day returns. I can start a cart or find similar.`,
          products: [p],
        };
      }
    }

    const hits = matchProducts(q);
    if (hits.length) {
      applyFilter(
        hits.map((p) => p.id),
        q
      );
      return {
        text: `I found **${hits.length}** catalog match${hits.length === 1 ? "" : "es"} — the wall is filtered to these SKUs only.`,
        products: hits,
      };
    }

    applyFilter(null, "");
    return {
      text: "I only recommend products in this storefront. Try “under ₹2,000”, “linen”, “headphones”, or an order ID like SF-284719.",
    };
  }

  function sendChatSafe(text) {
    const q = (text || "").trim();
    if (!q) return;
    appendMsg("user", q);
    $("chatInput").value = "";
    setTimeout(() => {
      const reply = replyFor(q);
      appendMsg("bot", reply.text);
      if (reply.products) appendSkuRow(reply.products);
    }, 280);
  }

  function openChat() {
    state.chatOpen = true;
    $("chatPanel").hidden = false;
    $("chatBackdrop").hidden = false;
    $("chatBubble").setAttribute("aria-expanded", "true");
  }

  function closeChat() {
    state.chatOpen = false;
    $("chatPanel").hidden = true;
    $("chatBackdrop").hidden = true;
    $("chatBubble").setAttribute("aria-expanded", "false");
  }

  function resetChat() {
    $("chatMessages").innerHTML = "";
    appendMsg("bot", D().chat.greeting);
    $("chatSuggestions").innerHTML = D()
      .chat.suggestions.map((s) => `<button type="button" class="chip-btn" data-q="${s}">${s}</button>`)
      .join("");
    $("chatSuggestions").querySelectorAll(".chip-btn").forEach((chip) => {
      chip.addEventListener("click", () => sendChatSafe(chip.dataset.q));
    });
  }

  function initChat() {
    resetChat();
    $("openChatBtn").addEventListener("click", openChat);
    $("chatBubble").addEventListener("click", openChat);
    $("chatClose").addEventListener("click", closeChat);
    $("chatBackdrop").addEventListener("click", closeChat);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && state.chatOpen) closeChat();
    });
    $("chatForm").addEventListener("submit", (e) => {
      e.preventDefault();
      sendChatSafe($("chatInput").value);
    });
    $("clearFilterBtn").addEventListener("click", () => {
      applyFilter(null, "");
      toast("Showing full catalog");
    });
    $("wismoClose").addEventListener("click", hideWismo);
    $("handoffDismiss").addEventListener("click", () => {
      $("handoffToast").hidden = true;
    });
    $("agentViewToggle").addEventListener("click", () => {
      state.opsOpen = !state.opsOpen;
      $("opsHud").hidden = !state.opsOpen;
      $("agentViewToggle").setAttribute("aria-pressed", String(state.opsOpen));
    });
  }

  function boot() {
    if (!window.RETAIL_DATA) {
      setTimeout(boot, 30);
      return;
    }
    initTheme();
    initTabs();
    renderHero();
    renderGrid();
    renderOps();
    initChat();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
