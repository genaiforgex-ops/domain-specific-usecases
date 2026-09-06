/* GenAIForge Manufacturing dashboard — plant schematic, floating PM copilot */
(function () {
  "use strict";

  const D = () => window.MFG_DATA;

  const state = {
    plantId: "pune",
    selectedAssetId: null,
    selectedLineId: null,
    copilotOpen: false,
    theme: "dark",
    oeeChart: null,
    sensorChart: null,
    alertAck: {},
    woStatus: {},
    dismissedStack: {},
  };

  const THEME_KEY = "gf-theme";

  function getTheme() {
    return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function themePalette() {
    const light = getTheme() === "light";
    const cs = getComputedStyle(document.documentElement);
    const v = (name) => cs.getPropertyValue(name).trim();
    return {
      accent: v("--accent") || (light ? "#1a9e92" : "#2ec4b6"),
      steel: v("--steel") || (light ? "#3d7a9e" : "#7eb0d0"),
      warn: v("--warn") || (light ? "#c48a12" : "#e8b84a"),
      danger: v("--danger") || (light ? "#d04444" : "#e85d5d"),
      ok: v("--ok") || (light ? "#2a9d5c" : "#4ecf8a"),
      chartText: v("--chart-text") || (light ? "#4a6278" : "#8fa3b5"),
      chartGrid: v("--chart-grid") || (light ? "rgba(60, 80, 100, 0.14)" : "rgba(148, 178, 198, 0.12)"),
      floorZoneFill: v("--floor-zone-fill") || (light ? "rgba(238, 242, 246, 0.95)" : "rgba(18, 26, 36, 0.92)"),
      floorCellTrack: v("--floor-cell-track") || (light ? "rgba(228, 234, 240, 0.9)" : "rgba(7, 10, 14, 0.5)"),
      floorGridStroke: v("--floor-grid-stroke") || (light ? "rgba(60, 80, 100, 0.1)" : "rgba(148, 178, 198, 0.06)"),
      floorPathStroke: v("--floor-path-stroke") || (light ? "rgba(26, 158, 146, 0.35)" : "rgba(46, 196, 182, 0.25)"),
      floorDotStroke: v("--floor-dot-stroke") || (light ? "#f4f7fa" : "#070a0e"),
      floorLabel: v("--floor-label") || (light ? "#6b8296" : "#8fa3b5"),
      floorTitle: v("--floor-title") || (light ? "#1a2836" : "#e8f0f6"),
    };
  }

  function updateThemeToggleUi() {
    const theme = getTheme();
    const btn = $("themeToggle");
    const label = $("themeToggleLabel");
    if (!btn) return;
    const isDark = theme === "dark";
    btn.setAttribute("aria-label", isDark ? "Switch to light mode" : "Switch to dark mode");
    btn.setAttribute("aria-pressed", isDark ? "false" : "true");
    if (label) label.textContent = isDark ? "Dark" : "Light";
    const meta = document.getElementById("themeColorMeta");
    if (meta) meta.setAttribute("content", isDark ? "#070a0e" : "#f4f7fa");
  }

  function applyTheme(theme, persist) {
    const next = theme === "light" ? "light" : "dark";
    state.theme = next;
    document.documentElement.setAttribute("data-theme", next);
    if (persist) localStorage.setItem(THEME_KEY, next);
    updateThemeToggleUi();
    chartDefaults();
    renderFloorSchematic();
    renderOeeChart();
    renderSensorChart();
  }

  function initTheme() {
    const stored = localStorage.getItem(THEME_KEY);
    const theme = stored === "light" ? "light" : "dark";
    state.theme = theme;
    document.documentElement.setAttribute("data-theme", theme);
    updateThemeToggleUi();
    $("themeToggle")?.addEventListener("click", () => {
      applyTheme(getTheme() === "dark" ? "light" : "dark", true);
    });
  }

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

  function fmtDelta(v, unit) {
    if (v == null) return "";
    const sign = v > 0 ? "+" : "";
    const cls = v > 0 ? "up" : v < 0 ? "down" : "";
    return `<span class="kpi-delta ${cls}">${sign}${v}${unit || ""}</span>`;
  }

  function cellColor(oee) {
    const light = getTheme() === "light";
    if (oee >= 85) return light ? "rgba(42, 157, 92, 0.88)" : "rgba(78, 207, 138, 0.85)";
    if (oee >= 70) return light ? "rgba(196, 138, 18, 0.85)" : "rgba(232, 184, 74, 0.8)";
    return light ? "rgba(208, 68, 68, 0.88)" : "rgba(232, 93, 93, 0.85)";
  }

  function statusStroke(status) {
    const p = themePalette();
    if (status === "critical") return p.danger;
    if (status === "watch") return p.warn;
    return p.ok;
  }

  function assetFill(status) {
    const p = themePalette();
    if (status === "critical") return p.danger;
    if (status === "watch") return p.warn;
    return p.ok;
  }

  function updateClock() {
    const el = $("clock");
    const now = new Date();
    el.dateTime = now.toISOString();
    el.textContent = now.toLocaleString("en-IN", {
      weekday: "short",
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  }

  function initPlantSelect() {
    const sel = $("plantSelect");
    sel.innerHTML = D()
      .plants.map((p) => `<option value="${p.id}">${p.name}</option>`)
      .join("");
    sel.value = state.plantId;
    sel.addEventListener("change", () => {
      state.plantId = sel.value;
      state.selectedLineId = null;
      state.dismissedStack = {};
      const assets = D().assets[state.plantId] || [];
      state.selectedAssetId = assets[0]?.id || null;
      renderAll();
    });
  }

  function renderKpis() {
    const k = D().kpis[state.plantId];
    const items = [
      { label: "OEE", value: `${k.oee}%`, delta: fmtDelta(k.oeeDelta, " pts"), cls: k.oee < 75 ? "danger" : "" },
      { label: "Availability", value: `${k.availability}%`, delta: fmtDelta(k.availabilityDelta, " pts") },
      { label: "Performance", value: `${k.performance}%`, delta: fmtDelta(k.performanceDelta, " pts") },
      { label: "Quality", value: `${k.quality}%`, delta: fmtDelta(k.qualityDelta, " pts") },
      {
        label: "Critical alerts",
        value: String(k.criticalAlerts),
        delta: `<span class="kpi-delta">active now</span>`,
        cls: k.criticalAlerts > 0 ? "danger" : "",
      },
      {
        label: "Predicted failures (7d)",
        value: String(k.predictedFailures7d),
        delta: `<span class="kpi-delta">if no intervention</span>`,
        cls: k.predictedFailures7d > 1 ? "warn" : "",
      },
    ];

    $("kpiStrip").innerHTML = items
      .map(
        (it) => `
      <div class="kpi ${it.cls || ""}">
        <div class="kpi-label">${it.label}</div>
        <div class="kpi-value">${it.value}</div>
        ${it.delta}
      </div>`
      )
      .join("");
  }

  function assetsOnLine(lineId) {
    return (D().assets[state.plantId] || []).filter((a) => a.line === lineId);
  }

  function renderFloorSchematic() {
    const schematic = D().schematic[state.plantId];
    const lines = D().lines[state.plantId] || [];
    const wrap = $("floorSchematic");
    if (!schematic) {
      wrap.innerHTML = "";
      return;
    }

    const p = themePalette();
    const lineMap = Object.fromEntries(lines.map((l) => [l.id, l]));

    const zones = schematic.zones
      .map((z) => {
        const line = lineMap[z.lineId];
        if (!line) return "";
        const active = state.selectedLineId === z.lineId;
        const assets = assetsOnLine(z.lineId);
        const assetDots = assets
          .slice(0, 4)
          .map((a, i) => {
            const dx = z.x + 16 + (i % 2) * 28;
            const dy = z.y + z.h - 22 - Math.floor(i / 2) * 14;
            const fill = assetFill(a.status);
            return `<circle class="asset-dot ${a.id === state.selectedAssetId ? "active" : ""}" data-asset="${a.id}" cx="${dx}" cy="${dy}" r="5" fill="${fill}" stroke="${p.floorDotStroke}" stroke-width="1.5"/>`;
          })
          .join("");

        return `
        <g class="floor-zone ${active ? "active" : ""}" data-line="${z.lineId}" role="button" tabindex="0" aria-label="${line.name}, OEE ${line.oee}%">
          <rect class="zone-bg" x="${z.x}" y="${z.y}" width="${z.w}" height="${z.h}" rx="8"
            fill="${p.floorZoneFill}" stroke="${statusStroke(line.status)}" stroke-width="${active ? 2.5 : 1.5}" opacity="${active ? 1 : 0.88}"/>
          <rect class="zone-cells" x="${z.x + 8}" y="${z.y + z.h - 18}" width="${z.w - 16}" height="8" rx="2" fill="${p.floorCellTrack}"/>
          ${line.cells
            .map((c, i) => {
              const cw = (z.w - 16) / line.cells.length - 2;
              const cx = z.x + 8 + i * (cw + 2);
              return `<rect x="${cx}" y="${z.y + z.h - 18}" width="${cw}" height="8" rx="2" fill="${cellColor(c)}"/>`;
            })
            .join("")}
          <text class="zone-id" x="${z.x + 12}" y="${z.y + 22}" fill="${p.floorLabel}" font-size="11" font-family="IBM Plex Mono, monospace">${line.id}</text>
          <text class="zone-name" x="${z.x + 12}" y="${z.y + 40}" fill="${p.floorTitle}" font-size="13" font-weight="600" font-family="IBM Plex Sans, sans-serif">${line.name}</text>
          <text class="zone-oee" x="${z.x + z.w - 12}" y="${z.y + 40}" fill="${p.accent}" font-size="14" font-weight="700" font-family="Syne, sans-serif" text-anchor="end">${line.oee}%</text>
          ${assetDots}
        </g>`;
      })
      .join("");

    const paths = (schematic.paths || [])
      .map((d) => `<path d="${d}" fill="none" stroke="${p.floorPathStroke}" stroke-width="2" stroke-dasharray="6 4"/>`)
      .join("");

    wrap.innerHTML = `
      <svg class="floor-svg" viewBox="${schematic.viewBox}" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
        <defs>
          <pattern id="floorGrid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M 24 0 L 0 0 0 24" fill="none" stroke="${p.floorGridStroke}" stroke-width="1"/>
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#floorGrid)"/>
        ${paths}
        ${zones}
      </svg>`;

    wrap.querySelectorAll(".floor-zone").forEach((zone) => {
      const select = () => selectLine(zone.dataset.line);
      zone.addEventListener("click", (e) => {
        if (e.target.closest(".asset-dot")) return;
        select();
      });
      zone.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          select();
        }
      });
    });

    wrap.querySelectorAll(".asset-dot").forEach((dot) => {
      dot.addEventListener("click", (e) => {
        e.stopPropagation();
        state.selectedAssetId = dot.dataset.asset;
        const asset = (D().assets[state.plantId] || []).find((a) => a.id === state.selectedAssetId);
        if (asset) state.selectedLineId = asset.line;
        renderFloorSchematic();
        renderAssets();
        renderSensorChart();
        renderLineDetail();
      });
    });

    renderLineDetail();
  }

  function selectLine(lineId) {
    state.selectedLineId = state.selectedLineId === lineId ? null : lineId;
    if (state.selectedLineId) {
      const onLine = assetsOnLine(state.selectedLineId);
      if (onLine.length && !onLine.find((a) => a.id === state.selectedAssetId)) {
        state.selectedAssetId = onLine[0].id;
      }
    }
    renderFloorSchematic();
    renderAssets();
    renderSensorChart();
    renderLines();
    renderLineDetail();
  }

  function renderLineDetail() {
    const detail = $("lineDetail");
    if (!state.selectedLineId) {
      detail.hidden = true;
      detail.innerHTML = "";
      $("floorSubtitle").textContent = "Click a line to highlight assets · cell OEE last shift";
      $("assetListSubtitle").textContent = "RUL · failure probability · click to inspect";
      return;
    }

    const line = (D().lines[state.plantId] || []).find((l) => l.id === state.selectedLineId);
    if (!line) {
      detail.hidden = true;
      return;
    }

    const assets = assetsOnLine(state.selectedLineId);
    detail.hidden = false;
    $("floorSubtitle").textContent = `${line.name} selected · ${assets.length} monitored assets`;
    $("assetListSubtitle").textContent = `Filtered to ${line.id} · click asset for sensors`;

    detail.innerHTML = `
      <div class="line-detail-head">
        <span class="status-dot status-${line.status}"></span>
        <strong>${line.name}</strong>
        <span class="line-detail-oee">${line.oee}% OEE</span>
        <button type="button" class="btn btn-sm btn-ghost" id="clearLine">Clear selection</button>
      </div>
      <div class="line-detail-assets">
        ${assets
          .map(
            (a) => `
          <button type="button" class="line-asset-chip ${a.id === state.selectedAssetId ? "active" : ""} ${a.status}" data-id="${a.id}">
            ${a.id} · ${a.name.split(" ").slice(-2).join(" ")} · risk ${a.risk}
          </button>`
          )
          .join("")}
      </div>`;

    $("clearLine")?.addEventListener("click", () => selectLine(state.selectedLineId));
    detail.querySelectorAll(".line-asset-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        state.selectedAssetId = chip.dataset.id;
        renderFloorSchematic();
        renderAssets();
        renderSensorChart();
      });
    });
  }

  function renderLines() {
    const lines = D().lines[state.plantId] || [];
    const filtered = state.selectedLineId ? lines.filter((l) => l.id === state.selectedLineId) : lines;

    $("lineHealth").innerHTML = filtered
      .map(
        (line) => `
      <div class="line-row ${state.selectedLineId === line.id ? "active" : ""}" data-line="${line.id}">
        <div>
          <span class="status-dot status-${line.status}"></span>
          <div class="line-name">${line.name}</div>
          <div class="line-id">${line.id}</div>
        </div>
        <div class="cells" title="Cell OEE">
          ${line.cells
            .map(
              (c) =>
                `<div class="cell" style="background:${cellColor(c)}" title="${c}% OEE"></div>`
            )
            .join("")}
        </div>
        <div class="line-oee">${line.oee}%</div>
      </div>`
      )
      .join("");

    $("lineHealth").querySelectorAll(".line-row").forEach((row) => {
      row.addEventListener("click", () => selectLine(row.dataset.line));
    });
  }

  function chartDefaults() {
    const p = themePalette();
    Chart.defaults.color = p.chartText;
    Chart.defaults.borderColor = p.chartGrid;
    Chart.defaults.font.family = "'IBM Plex Sans', system-ui, sans-serif";
  }

  function chartColors() {
    const p = themePalette();
    const light = getTheme() === "light";
    return {
      oeeLine: p.accent,
      oeeFill: light ? "rgba(26, 158, 146, 0.14)" : "rgba(46, 196, 182, 0.12)",
      plannedBar: light ? "rgba(61, 122, 158, 0.55)" : "rgba(126, 176, 208, 0.45)",
      unplannedBar: light ? "rgba(208, 68, 68, 0.6)" : "rgba(232, 93, 93, 0.55)",
      vib: p.accent,
      temp: p.warn,
      amp: p.steel,
    };
  }

  function renderOeeChart() {
    const t = D().trends[state.plantId];
    const ctx = $("oeeChart").getContext("2d");
    const c = chartColors();
    if (state.oeeChart) state.oeeChart.destroy();

    state.oeeChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: t.labels,
        datasets: [
          {
            type: "line",
            label: "OEE %",
            data: t.oee,
            borderColor: c.oeeLine,
            backgroundColor: c.oeeFill,
            fill: true,
            tension: 0.35,
            yAxisID: "y",
            pointRadius: 2,
            borderWidth: 2,
            order: 0,
          },
          {
            type: "bar",
            label: "Planned DT (h)",
            data: t.plannedDt,
            backgroundColor: c.plannedBar,
            yAxisID: "y1",
            order: 1,
            borderRadius: 3,
          },
          {
            type: "bar",
            label: "Unplanned DT (h)",
            data: t.unplannedDt,
            backgroundColor: c.unplannedBar,
            yAxisID: "y1",
            order: 2,
            borderRadius: 3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 10, boxHeight: 10, padding: 12, font: { size: 11 } },
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 0, font: { size: 10 } } },
          y: {
            position: "left",
            min: 50,
            max: 100,
            title: { display: true, text: "OEE %", font: { size: 10 } },
            ticks: { font: { size: 10 } },
          },
          y1: {
            position: "right",
            grid: { drawOnChartArea: false },
            title: { display: true, text: "Hours", font: { size: 10 } },
            ticks: { font: { size: 10 } },
          },
        },
      },
    });
  }

  function renderAssets() {
    let assets = D().assets[state.plantId] || [];
    if (state.selectedLineId) {
      assets = assets.filter((a) => a.line === state.selectedLineId);
    }
    if (!state.selectedAssetId || !assets.find((a) => a.id === state.selectedAssetId)) {
      state.selectedAssetId = assets[0]?.id || null;
    }

    $("assetList").innerHTML = assets.length
      ? assets
          .map(
            (a) => `
      <div class="asset-row ${a.id === state.selectedAssetId ? "active" : ""}" data-id="${a.id}" role="listitem">
        <div>
          <div class="asset-name"><span class="status-dot status-${a.status}"></span>${a.name}</div>
          <div class="asset-meta">${a.id} · Line ${a.line} · ${a.failureMode}</div>
        </div>
        <div class="asset-risk">
          <div class="risk-score ${a.status}">${a.risk}</div>
          <div class="rul">RUL ${a.rulHours}h</div>
        </div>
      </div>`
          )
          .join("")
      : `<p class="empty-hint">No assets on selected line.</p>`;

    $("assetList").querySelectorAll(".asset-row").forEach((row) => {
      row.addEventListener("click", () => {
        state.selectedAssetId = row.dataset.id;
        const asset = (D().assets[state.plantId] || []).find((a) => a.id === state.selectedAssetId);
        if (asset) state.selectedLineId = asset.line;
        renderFloorSchematic();
        renderAssets();
        renderSensorChart();
        renderLineDetail();
        renderLines();
      });
    });
  }

  function getSensorSeries(assetId) {
    const series = D().sensorSeries[assetId];
    if (series) return series;

    const asset = (D().assets[state.plantId] || []).find((a) => a.id === assetId);
    if (!asset) return null;

    const labels = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, "0")}:00`);
    const vib = [];
    const temp = [];
    const amp = [];
    for (let i = 0; i < 24; i++) {
      const t = i / 23;
      vib.push(+(asset.vibration * (0.55 + 0.45 * t) + Math.sin(i / 3) * 0.15).toFixed(2));
      temp.push(+(asset.temp * (0.7 + 0.3 * t) + Math.cos(i / 4) * 0.8).toFixed(1));
      amp.push(+(asset.current * (0.65 + 0.35 * t) + Math.sin(i / 5) * 0.2).toFixed(2));
    }
    return { labels, vibration: vib, temperature: temp, current: amp };
  }

  function renderSensorChart() {
    const asset = (D().assets[state.plantId] || []).find((a) => a.id === state.selectedAssetId);
    const series = getSensorSeries(state.selectedAssetId);

    $("sensorSubtitle").textContent = asset
      ? `${asset.name} · 24h trends`
      : "Select an asset";

    $("sensorMeta").innerHTML = asset
      ? `
      <span><strong>${asset.id}</strong></span>
      <span>Vib <strong>${asset.vibration}</strong> mm/s</span>
      <span>Temp <strong>${asset.temp}</strong> °C</span>
      <span>Current <strong>${asset.current}</strong> A</span>
      <span>RUL <strong>${asset.rulHours}h</strong></span>
      <span>Risk <strong>${asset.risk}</strong></span>`
      : "";

    const ctx = $("sensorChart").getContext("2d");
    if (state.sensorChart) state.sensorChart.destroy();
    if (!series) return;

    const c = chartColors();
    state.sensorChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: series.labels,
        datasets: [
          {
            label: "Vibration",
            data: series.vibration,
            borderColor: c.vib,
            backgroundColor: "transparent",
            yAxisID: "y",
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2,
          },
          {
            label: "Temp °C",
            data: series.temperature,
            borderColor: c.temp,
            backgroundColor: "transparent",
            yAxisID: "y1",
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2,
          },
          {
            label: "Current A",
            data: series.current,
            borderColor: c.amp,
            backgroundColor: "transparent",
            yAxisID: "y1",
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 1.5,
            borderDash: [4, 3],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: { maxTicksLimit: 8, font: { size: 10 } },
          },
          y: {
            position: "left",
            title: { display: true, text: "mm/s", font: { size: 10 } },
            ticks: { font: { size: 10 } },
          },
          y1: {
            position: "right",
            grid: { drawOnChartArea: false },
            title: { display: true, text: "°C / A", font: { size: 10 } },
            ticks: { font: { size: 10 } },
          },
        },
      },
    });
  }

  function renderAiStack() {
    const alerts = (D().alerts[state.plantId] || []).filter((a) => {
      const acked = state.alertAck[a.id] ?? a.acknowledged;
      return !acked && !state.dismissedStack[a.id];
    });

    const cards = [];
    alerts.slice(0, 3).forEach((a) => {
      cards.push({
        id: a.id,
        type: "alert",
        severity: a.severity,
        title: a.title,
        detail: a.detail,
        eta: a.eta,
        prompt: `Explain alert ${a.id} for ${a.assetId}`,
      });
    });

    if (cards.length < 2) {
      const insight = D().aiInsights[state.plantId];
      if (insight && !state.dismissedStack["insight"]) {
        cards.push({
          id: "insight",
          type: "insight",
          severity: "medium",
          title: insight.title,
          detail: insight.detail,
          prompt: insight.prompt,
        });
      }
    }

    $("aiStackCards").innerHTML = cards.length
      ? cards
          .map(
            (c) => `
        <article class="stack-card ${c.severity} ${c.type}" data-id="${c.id}">
          <div class="stack-card-top">
            <span class="stack-type">${c.type === "insight" ? "AI insight" : c.severity}</span>
            <button type="button" class="stack-dismiss" data-id="${c.id}" aria-label="Dismiss">×</button>
          </div>
          <h3 class="stack-title">${c.title}</h3>
          <p class="stack-detail">${c.detail}</p>
          <div class="stack-actions">
            ${c.eta ? `<span class="eta">${c.eta}</span>` : ""}
            <button type="button" class="btn btn-sm ask-copilot" data-prompt="${c.prompt.replace(/"/g, "&quot;")}">Ask copilot</button>
            ${
              c.type === "alert"
                ? `<button type="button" class="btn btn-sm btn-accent ack-btn" data-id="${c.id}">Acknowledge</button>`
                : ""
            }
          </div>
        </article>`
          )
          .join("")
      : `<p class="stack-empty">No active recommendations — plant stable.</p>`;

    $("aiStackCards").querySelectorAll(".ack-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.alertAck[btn.dataset.id] = true;
        toast("Alert acknowledged — logged for audit trail");
        renderAiStack();
      });
    });

    $("aiStackCards").querySelectorAll(".stack-dismiss").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.dismissedStack[btn.dataset.id] = true;
        renderAiStack();
      });
    });

    $("aiStackCards").querySelectorAll(".ask-copilot").forEach((btn) => {
      btn.addEventListener("click", () => {
        openCopilot();
        sendCopilot(btn.dataset.prompt);
      });
    });
  }

  function renderWorkOrders() {
    const wos = D().workOrders[state.plantId] || [];
    $("woBody").innerHTML = wos
      .map((w) => {
        const status = state.woStatus[w.id] || w.status;
        const canApprove = status === "draft";
        return `
        <tr>
          <td><code>${w.id}</code></td>
          <td>${w.asset}</td>
          <td>${w.title}</td>
          <td class="prio prio-${w.priority}">${w.priority}</td>
          <td>${w.source}</td>
          <td><span class="wo-status ${status}">${status}</span></td>
          <td>
            ${
              canApprove
                ? `<button type="button" class="btn btn-sm btn-accent approve-wo" data-id="${w.id}">Approve WO</button>`
                : ""
            }
          </td>
        </tr>`;
      })
      .join("");

    $("woBody").querySelectorAll(".approve-wo").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.woStatus[btn.dataset.id] = "approved";
        toast(`${btn.dataset.id} approved by human — ready to schedule`);
        renderWorkOrders();
      });
    });
  }

  /* ——— Copilot ——— */
  function formatMsg(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  function appendMsg(role, text) {
    const box = $("copilotMessages");
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.innerHTML = formatMsg(text);
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  function replyFor(input) {
    const replies = D().copilot.replies;
    for (const r of replies) {
      if (r.match.test(input)) return r.text;
    }
    if (/alert|al-\d+/i.test(input)) {
      return D().copilot.replies.find((r) => /alert/i.test(r.match.source))?.text || D().copilot.fallback;
    }
    return D().copilot.fallback;
  }

  function sendCopilot(text) {
    const q = (text || "").trim();
    if (!q) return;
    appendMsg("user", q);
    $("copilotInput").value = "";
    setTimeout(() => appendMsg("bot", replyFor(q)), 420);
  }

  function openCopilot() {
    state.copilotOpen = true;
    const panel = $("copilot");
    panel.hidden = false;
    requestAnimationFrame(() => panel.classList.add("open"));
    $("expandChat").setAttribute("aria-expanded", "true");
    $("expandChat").textContent = "Minimize";
    document.body.classList.add("copilot-open");
  }

  function closeCopilot() {
    state.copilotOpen = false;
    const panel = $("copilot");
    panel.classList.remove("open");
    $("expandChat").setAttribute("aria-expanded", "false");
    $("expandChat").textContent = "Expand chat";
    document.body.classList.remove("copilot-open");
    setTimeout(() => {
      if (!state.copilotOpen) panel.hidden = true;
    }, 360);
  }

  function toggleCopilot() {
    if (state.copilotOpen) closeCopilot();
    else openCopilot();
  }

  function initCopilot() {
    const c = D().copilot;
    $("copilotMessages").innerHTML = "";
    appendMsg("bot", c.welcome);

    $("copilotSuggestions").innerHTML = c.suggestions
      .map((s) => `<button type="button" class="chip" data-q="${s.replace(/"/g, "&quot;")}">${s}</button>`)
      .join("");

    $("copilotSuggestions").querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        openCopilot();
        sendCopilot(chip.dataset.q);
      });
    });

    $("expandChat").addEventListener("click", toggleCopilot);
    $("copilotClose").addEventListener("click", closeCopilot);

    $("copilotForm").addEventListener("submit", (e) => {
      e.preventDefault();
      sendCopilot($("copilotInput").value);
    });
  }

  function renderAll() {
    renderFloorSchematic();
    renderKpis();
    renderLines();
    renderOeeChart();
    renderAssets();
    renderSensorChart();
    renderAiStack();
    renderWorkOrders();
  }

  function boot() {
    if (!window.MFG_DATA || typeof Chart === "undefined") {
      setTimeout(boot, 40);
      return;
    }
    chartDefaults();
    initTheme();
    initPlantSelect();
    const assets = D().assets[state.plantId] || [];
    state.selectedAssetId = assets[0]?.id || null;
    initCopilot();
    renderAll();
    updateClock();
    setInterval(updateClock, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
