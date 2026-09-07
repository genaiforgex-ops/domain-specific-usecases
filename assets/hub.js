(function () {
  var USECASES = [
    {
      id: "creatives",
      href: "Creatives/index.html",
      product: "Campaign Studio",
      vertical: "Creatives",
      audience: "Marketing · brand · agencies",
      blurb: "Brief → copy → design with brand guardrails, HITL approvals, and ROI.",
      accent: "#b8956c",
      flagship: true,
    },
    {
      id: "vendor",
      href: "VendorDueDiligence/index.html",
      product: "Vendor Due Diligence",
      vertical: "TPRM",
      audience: "Risk · procurement · compliance",
      blurb: "Register → screen → decide → monitor, with scoring and an audit pack.",
      accent: "#3dd68c",
      flagship: true,
    },
    {
      id: "legal",
      href: "LegalWorkflow/index.html",
      product: "LegalOS + LegalBot",
      vertical: "Legal",
      audience: "Legal · CLM · GC office",
      blurb: "MSA automation, playbook-cited LegalBot, obligations, and a trust center.",
      accent: "#d4a017",
      flagship: true,
    },
    {
      id: "banking",
      href: "Banking/index.html",
      product: "Voice Command Center",
      vertical: "BFSI",
      audience: "Collections · advisory",
      blurb: "Live call floor, DPD playbooks, customer 360, RBI/SEBI compliance rails.",
      accent: "#12b76a",
    },
    {
      id: "healthcare",
      href: "Healthcare/index.html",
      product: "Patient Access",
      vertical: "Healthcare",
      audience: "Clinics · patient access",
      blurb: "24/7 booking, no-show risk, protocol intake — assistive, non-diagnostic.",
      accent: "#2a9d8f",
    },
    {
      id: "insurance",
      href: "Insurance/index.html",
      product: "Agentic Claims & FNOL",
      vertical: "Insurance",
      audience: "Insurers · claims ops",
      blurb: "Multi-stage claim journey: extract, validate, assess — settle or escalate.",
      accent: "#2aa198",
    },
    {
      id: "manufacturing",
      href: "Manufacturing/index.html",
      product: "Predictive Maintenance",
      vertical: "Manufacturing",
      audience: "Plant ops · reliability",
      blurb: "Plant schematic, OEE, risk-ranked assets, PM copilot with WO approval.",
      accent: "#2ec4b6",
    },
    {
      id: "realestate",
      href: "RealEstate/index.html",
      product: "Sales Command Center",
      vertical: "Real Estate",
      audience: "Developers · sales",
      blurb: "Lead qualify, site-plan heat, unit match, and visit booking in under 60s.",
      accent: "#c9a227",
    },
    {
      id: "retail",
      href: "Retail/index.html",
      product: "Conversational Commerce",
      vertical: "Retail",
      audience: "Retail · CX",
      blurb: "Co-browse catalog, order tracking (WISMO), returns, and stylist handoff.",
      accent: "#e07a5f",
    },
  ];

  var fileProtocol = location.protocol === "file:";
  var grid = document.getElementById("usecaseGrid");
  var stage = document.getElementById("stage");
  var stageFrame = document.getElementById("stageFrame");
  var stageTitle = document.getElementById("stageTitle");
  var stageMeta = document.getElementById("stageMeta");
  var stageOpen = document.getElementById("stageOpen");
  var backBtn = document.getElementById("backBtn");
  var themeToggle = document.getElementById("themeToggle");
  var fileBanner = document.getElementById("fileBanner");
  var countEl = document.getElementById("demoCount");

  function byId(id) {
    for (var i = 0; i < USECASES.length; i++) {
      if (USECASES[i].id === id) return USECASES[i];
    }
    return null;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderGrid() {
    if (countEl) countEl.textContent = String(USECASES.length);

    grid.innerHTML = USECASES.map(function (u, i) {
      var n = String(i + 1).padStart(2, "0");
      var flag = u.flagship ? '<span class="flag">Featured</span>' : "";
      var preview = fileProtocol
        ? '<div class="preview-fallback"><span>' + escapeHtml(u.product) + "</span></div>"
        : '<div class="preview-clip" data-src="' +
          escapeHtml(u.href) +
          '"><div class="preview-shimmer"></div></div>';

      return (
        '<article class="window" data-id="' +
        u.id +
        '" style="--i:' +
        i +
        '" tabindex="0" role="button" aria-label="Open ' +
        escapeHtml(u.product) +
        '">' +
        '<div class="window-chrome">' +
        '<span class="index">' +
        n +
        "</span>" +
        '<span class="chrome-title">' +
        escapeHtml(u.vertical) +
        "</span>" +
        flag +
        "</div>" +
        preview +
        '<div class="window-meta">' +
        "<h2>" +
        escapeHtml(u.product) +
        "</h2>" +
        '<p class="audience">' +
        escapeHtml(u.audience) +
        "</p>" +
        '<p class="blurb">' +
        escapeHtml(u.blurb) +
        "</p>" +
        '<span class="open-hint">Enter workspace <span aria-hidden="true">→</span></span>' +
        "</div>" +
        "</article>"
      );
    }).join("");
  }

  function lazyPreviews() {
    if (fileProtocol) return;
    var clips = grid.querySelectorAll(".preview-clip");
    if (!("IntersectionObserver" in window)) {
      clips.forEach(mountPreview);
      return;
    }
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            mountPreview(entry.target);
            io.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "120px" }
    );
    clips.forEach(function (el) {
      io.observe(el);
    });
  }

  function mountPreview(clip) {
    if (clip.querySelector("iframe")) return;
    var src = clip.getAttribute("data-src");
    var frame = document.createElement("iframe");
    frame.src = src;
    frame.title = "Live preview";
    frame.tabIndex = -1;
    frame.setAttribute("loading", "lazy");
    frame.addEventListener("load", function () {
      clip.classList.add("is-loaded");
    });
    clip.appendChild(frame);
  }

  function openUsecase(u, pushHash) {
    if (!u) return;
    if (fileProtocol) {
      window.location.href = u.href;
      return;
    }
    stageTitle.textContent = u.product;
    stageMeta.textContent = u.vertical + " · " + u.audience;
    stageOpen.href = u.href;
    stage.style.setProperty("--accent", u.accent);
    if (stageFrame.getAttribute("src") !== u.href) {
      stageFrame.src = u.href;
    }
    stage.classList.add("is-open");
    stage.setAttribute("aria-hidden", "false");
    document.body.classList.add("stage-open");
    backBtn.focus();
    if (pushHash !== false) {
      history.pushState({ id: u.id }, "", "#" + u.id);
    }
  }

  function closeStage(pushHash) {
    stage.classList.remove("is-open");
    stage.setAttribute("aria-hidden", "true");
    document.body.classList.remove("stage-open");
    stageFrame.removeAttribute("src");
    if (pushHash !== false) {
      history.pushState({}, "", location.pathname + location.search);
    }
  }

  function openFromHash() {
    var id = (location.hash || "").replace(/^#/, "");
    if (!id) {
      if (stage.classList.contains("is-open")) closeStage(false);
      return;
    }
    var u = byId(id);
    if (u) openUsecase(u, false);
  }

  grid.addEventListener("click", function (e) {
    var card = e.target.closest(".window");
    if (!card) return;
    openUsecase(byId(card.getAttribute("data-id")));
  });

  grid.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var card = e.target.closest(".window");
    if (!card) return;
    e.preventDefault();
    openUsecase(byId(card.getAttribute("data-id")));
  });

  backBtn.addEventListener("click", function () {
    closeStage();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && stage.classList.contains("is-open")) {
      closeStage();
    }
  });

  window.addEventListener("popstate", openFromHash);

  themeToggle.addEventListener("click", function () {
    var root = document.documentElement;
    var light = root.classList.contains("gf-theme-light");
    root.classList.toggle("gf-theme-light", !light);
    root.classList.toggle("gf-theme-dark", light);
    localStorage.setItem("gf-theme", light ? "dark" : "light");
    var meta = document.getElementById("themeColorMeta");
    if (meta) meta.setAttribute("content", light ? "#050505" : "#f6f5f2");
  });

  if (fileBanner) {
    fileBanner.hidden = !fileProtocol;
  }

  renderGrid();
  lazyPreviews();
  openFromHash();
})();
