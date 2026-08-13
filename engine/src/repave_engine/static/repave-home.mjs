/**
 * Home / catalog page interactions (native ES module, no bundler).
 * Loaded only from index.html. Shared chrome stays in repave.js.
 */
const RECENT_PATHS_KEY = "repave:recentPaths";
/** Last N opened golden paths in the compact quick strip. */
const RECENT_PATHS_MAX = 3;

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function supportsViewTransitions() {
  return (
    typeof document.startViewTransition === "function" && !prefersReducedMotion()
  );
}

function fuzzyMatchScore(query, label) {
  const q = (query || "").toLowerCase().trim();
  const text = (label || "").toLowerCase();
  if (!q) {
    return 1;
  }
  let qi = 0;
  for (let ti = 0; ti < text.length && qi < q.length; ti += 1) {
    if (text.charAt(ti) === q.charAt(qi)) {
      qi += 1;
    }
  }
  if (qi !== q.length) {
    return 0;
  }
  return q.length / Math.max(text.length, 1);
}

function readLastRun() {
  try {
    const raw = sessionStorage.getItem("repave:lastRun");
    if (!raw) {
      return null;
    }
    return JSON.parse(raw);
  } catch (_err) {
    return null;
  }
}

function readRecentPaths() {
  try {
    const raw = localStorage.getItem(RECENT_PATHS_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (_err) {
    return [];
  }
}

function writeRecentPaths(entries) {
  try {
    localStorage.setItem(RECENT_PATHS_KEY, JSON.stringify(entries.slice(0, RECENT_PATHS_MAX)));
  } catch (_err) {
    /* ignore quota / private mode */
  }
}

function recordRecentPath(entry) {
  if (!entry || !entry.href || !entry.name) {
    return;
  }
  const next = [
    entry,
    ...readRecentPaths().filter((item) => item.href !== entry.href),
  ].slice(0, RECENT_PATHS_MAX);
  writeRecentPaths(next);
}

function initHomeResumeChip() {
  const mount = document.getElementById("home-resume-chip");
  const quick = document.querySelector("[data-home-quick]");
  if (!mount) {
    return;
  }
  mount.replaceChildren();
  const run = readLastRun();
  if (!run || !run.blueprint) {
    mount.hidden = true;
    syncHomeQuickVisibility(quick);
    return;
  }
  const href = "/blueprints/" + encodeURIComponent(run.blueprint);
  const label = document.createElement("span");
  label.className = "home-quick__label muted";
  label.textContent = "Resume";
  const link = document.createElement("a");
  link.className = "home-quick__link";
  link.href = href;
  const code = document.createElement("code");
  code.textContent = run.blueprint;
  link.append(code);
  mount.append(label, link);
  mount.hidden = false;
  syncHomeQuickVisibility(quick);
}

function syncHomeQuickVisibility(quick) {
  if (!quick) {
    return;
  }
  const resume = document.getElementById("home-resume-chip");
  const list = quick.querySelector("[data-recent-paths-list]");
  const hasResume = resume && !resume.hidden && resume.childElementCount > 0;
  const hasRecent = list && list.children.length > 0;
  quick.hidden = !(hasResume || hasRecent);
}

function initCatalogCardMotion() {
  const cards = document.querySelectorAll("[data-catalog-card]");
  if (!cards.length || prefersReducedMotion()) {
    return;
  }
  cards.forEach((card) => {
    card.addEventListener("mousemove", (event) => {
      const rect = card.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;
      card.classList.add("is-tilted");
      card.style.transform =
        "perspective(700px) rotateX(" +
        (-y * 4).toFixed(2) +
        "deg) rotateY(" +
        (x * 4).toFixed(2) +
        "deg) translateY(-2px)";
    });
    card.addEventListener("mouseleave", () => {
      card.classList.remove("is-tilted");
      card.style.transform = "";
    });
  });
}

function runWithViewTransition(update) {
  if (!supportsViewTransitions()) {
    update();
    return;
  }
  document.startViewTransition(update);
}

function syncSearchToUrl(query) {
  const url = new URL(window.location.href);
  if (query) {
    url.searchParams.set("q", query);
  } else {
    url.searchParams.delete("q");
  }
  const next = url.pathname + url.search + url.hash;
  const current = window.location.pathname + window.location.search + window.location.hash;
  if (next !== current) {
    history.replaceState(null, "", next);
  }
}

function initCatalogSearch() {
  const root = document.querySelector("[data-catalog-search]");
  const input = document.querySelector("[data-catalog-search-input]");
  if (!root || !input) {
    return;
  }
  const meta = root.querySelector("[data-catalog-search-meta]");
  const emptyState = document.getElementById("catalog-search-empty");
  const cards = Array.from(document.querySelectorAll("[data-catalog-card]"));
  const groups = document.querySelectorAll("[data-catalog-group]");
  let activeIndex = -1;

  if (window.location.hash === "#golden-paths") {
    const goldenPaths = document.getElementById("golden-paths");
    if (goldenPaths) {
      goldenPaths.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  const params = new URLSearchParams(window.location.search);
  const initialQuery = params.get("q");
  if (initialQuery) {
    input.value = initialQuery;
  }

  function visibleRows() {
    return cards
      .map((card) => card.closest("[data-catalog-item]") || card)
      .filter((row) => !row.hidden);
  }

  function setActiveRow(index) {
    const rows = visibleRows();
    rows.forEach((row) => {
      row.classList.remove("is-keyboard-active");
      const link = row.querySelector("[data-catalog-card]") || row;
      link.setAttribute("tabindex", "-1");
    });
    if (!rows.length) {
      activeIndex = -1;
      return;
    }
    activeIndex = ((index % rows.length) + rows.length) % rows.length;
    const active = rows[activeIndex];
    active.classList.add("is-keyboard-active");
    const link = active.querySelector("[data-catalog-card]") || active;
    link.setAttribute("tabindex", "0");
    link.focus({ preventScroll: false });
    active.scrollIntoView({ block: "nearest" });
  }

  function applyFilter() {
    const query = (input.value || "").toLowerCase().trim();
    const terms = query ? query.split(/\s+/).filter(Boolean) : [];
    let visibleCards = 0;
    const scored = [];

    cards.forEach((card) => {
      const haystack = (card.getAttribute("data-search-text") || "").toLowerCase();
      const name = (card.getAttribute("data-peek-name") || card.textContent || "").trim();
      let match = terms.length === 0;
      let score = 0;
      if (terms.length > 0) {
        const allPresent = terms.every((term) => haystack.includes(term));
        const fuzzy = fuzzyMatchScore(query, name) + fuzzyMatchScore(query, haystack) * 0.5;
        match = allPresent || fuzzy > 0;
        score = (allPresent ? 1 : 0) + fuzzy;
      }
      const row = card.closest("[data-catalog-item]");
      if (row) {
        row.hidden = !match;
        if (match) {
          scored.push({ row, score });
        }
      } else {
        card.hidden = !match;
      }
      if (match) {
        visibleCards += 1;
      }
    });

    if (terms.length > 0 && scored.length > 1) {
      scored.sort((a, b) => b.score - a.score);
      scored.forEach(({ row }) => {
        const parent = row.parentElement;
        if (parent) {
          parent.append(row);
        }
      });
    }

    groups.forEach((group) => {
      const items = group.querySelectorAll("[data-catalog-item]");
      let anyVisible = false;
      items.forEach((item) => {
        if (!item.hidden) {
          anyVisible = true;
        }
      });
      group.hidden = !anyVisible && terms.length > 0;
    });

    if (meta) {
      if (terms.length === 0) {
        meta.hidden = true;
      } else {
        meta.hidden = false;
        meta.textContent =
          visibleCards === 1 ? "1 artifact matches" : visibleCards + " artifacts match";
      }
    }
    if (emptyState) {
      emptyState.hidden = !(terms.length > 0 && visibleCards === 0);
    }
    activeIndex = -1;
    syncSearchToUrl(query);
  }

  function applyFilterWithTransition() {
    runWithViewTransition(applyFilter);
  }

  input.addEventListener("input", applyFilterWithTransition);

  document.addEventListener("keydown", (event) => {
    const tag = (event.target && event.target.tagName) || "";
    const typing =
      tag === "INPUT" ||
      tag === "TEXTAREA" ||
      tag === "SELECT" ||
      (event.target && event.target.isContentEditable);
    if (event.key === "/" && !typing && !event.metaKey && !event.ctrlKey && !event.altKey) {
      event.preventDefault();
      input.focus();
      return;
    }
    if (event.target !== input && !event.target.closest?.("[data-catalog-item]")) {
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveRow(activeIndex + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveRow(activeIndex <= 0 ? visibleRows().length - 1 : activeIndex - 1);
    } else if (event.key === "Enter" && activeIndex >= 0) {
      const rows = visibleRows();
      const link = rows[activeIndex]?.querySelector("a[href]");
      if (link) {
        event.preventDefault();
        link.click();
      }
    }
  });

  applyFilter();
}

function initCatalogPeeks() {
  const supportsPopover = "popover" in HTMLElement.prototype;
  const cards = document.querySelectorAll("[data-catalog-card][data-peek-name]");
  cards.forEach((card, index) => {
    const row = card.closest("[data-catalog-item]");
    if (!row || row.querySelector("[data-catalog-peek]")) {
      return;
    }
    const popoverId = "catalog-peek-" + index;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "catalog-inventory__peek-btn btn btn--ghost btn--sm";
    btn.textContent = "Peek";
    btn.setAttribute("aria-label", "Peek at " + (card.getAttribute("data-peek-name") || "golden path"));
    if (supportsPopover) {
      btn.setAttribute("popovertarget", popoverId);
    } else {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        const panel = document.getElementById(popoverId);
        if (panel) {
          panel.hidden = !panel.hidden;
        }
      });
    }

    const panel = document.createElement("div");
    panel.id = popoverId;
    panel.className = "catalog-peek";
    panel.setAttribute("data-catalog-peek", "");
    if (supportsPopover) {
      panel.setAttribute("popover", "auto");
    } else {
      panel.hidden = true;
    }

    const title = document.createElement("h3");
    title.className = "catalog-peek__title";
    title.textContent = card.getAttribute("data-peek-name") || "";
    panel.append(title);

    const desc = card.getAttribute("data-peek-description") || "";
    if (desc) {
      const p = document.createElement("p");
      p.className = "catalog-peek__desc muted";
      p.textContent = desc;
      panel.append(p);
    }

    const meta = document.createElement("dl");
    meta.className = "catalog-peek__meta";
    const pairs = [
      ["Version", card.getAttribute("data-peek-version")],
      ["Gates", card.getAttribute("data-peek-gates")],
      ["Standard", card.getAttribute("data-peek-standard")],
    ];
    pairs.forEach(([label, value]) => {
      if (!value) {
        return;
      }
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      meta.append(dt, dd);
    });
    panel.append(meta);

    const openLink = document.createElement("a");
    openLink.className = "btn btn--primary btn--sm";
    openLink.href = card.getAttribute("href") || "#";
    openLink.textContent = "Open golden path";
    panel.append(openLink);

    const actions = document.createElement("div");
    actions.className = "catalog-inventory__row-actions";
    actions.append(btn);
    row.append(actions, panel);
  });
}

function initCatalogNavigation() {
  document.querySelectorAll("[data-catalog-card]").forEach((card) => {
    card.addEventListener("click", () => {
      const name = card.getAttribute("data-peek-name") || card.textContent.trim();
      const href = card.getAttribute("href");
      if (href) {
        recordRecentPath({
          name,
          href,
          version: card.getAttribute("data-peek-version") || "",
        });
      }
      if (!supportsViewTransitions()) {
        return;
      }
      card.style.viewTransitionName = "catalog-card";
    });
  });
}

function initRecentRail() {
  const quick = document.querySelector("[data-home-quick]");
  const list = document.querySelector("[data-recent-paths-list]");
  if (!list) {
    return;
  }
  list.replaceChildren();
  const entries = readRecentPaths().slice(0, RECENT_PATHS_MAX);
  if (!entries.length) {
    syncHomeQuickVisibility(quick);
    return;
  }
  const label = document.createElement("li");
  label.className = "home-quick__label-item";
  const labelSpan = document.createElement("span");
  labelSpan.className = "home-quick__label muted";
  labelSpan.textContent = "Recent";
  label.append(labelSpan);
  list.append(label);
  entries.forEach((entry) => {
    if (!entry || !entry.href || !entry.name) {
      return;
    }
    const li = document.createElement("li");
    li.className = "home-quick__item";
    const a = document.createElement("a");
    a.className = "home-quick__link";
    a.href = entry.href;
    a.textContent = entry.name;
    li.append(a);
    list.append(li);
  });
  syncHomeQuickVisibility(quick);
}

class RepaveMetric extends HTMLElement {
  connectedCallback() {
    if (this._booted) {
      return;
    }
    this._booted = true;
    const target = Number(this.getAttribute("value") || this.textContent || "0");
    if (!Number.isFinite(target)) {
      return;
    }
    this.setAttribute("value", String(target));
    if (prefersReducedMotion() || typeof this.animate !== "function") {
      this.textContent = String(target);
      return;
    }
    const state = { n: 0 };
    this.textContent = "0";
    const animation = this.animate([{ opacity: 0.65 }, { opacity: 1 }], {
      duration: 700,
      easing: "ease-out",
      fill: "forwards",
    });
    const start = performance.now();
    const duration = 900;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      state.n = Math.round(target * eased);
      this.textContent = String(state.n);
      if (t < 1) {
        requestAnimationFrame(tick);
      } else {
        this.textContent = String(target);
      }
    };
    requestAnimationFrame(tick);
    void animation;
  }
}

function registerMetricElement() {
  if (customElements.get("repave-metric")) {
    return;
  }
  customElements.define("repave-metric", RepaveMetric);
}

function boot() {
  registerMetricElement();
  initHomeResumeChip();
  initCatalogCardMotion();
  initCatalogSearch();
  initCatalogPeeks();
  initCatalogNavigation();
  initRecentRail();
}

window.repaveHome = {
  refreshResumeChip: initHomeResumeChip,
  refreshRecentRail: initRecentRail,
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
