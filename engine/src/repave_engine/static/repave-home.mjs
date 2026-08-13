/**
 * Home / catalog page interactions (native ES module, no bundler).
 * Loaded only from index.html. Shared chrome stays in repave.js.
 */
import {
  initCatalogCardMotion,
  initCatalogSearch,
  prefersReducedMotion,
  supportsViewTransitions,
} from "./repave-catalog.mjs";

const RECENT_PATHS_KEY = "repave:recentPaths";
/** Last N opened golden paths in the compact quick strip. */
const RECENT_PATHS_MAX = 3;

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
  initCatalogSearch({ scrollTargetId: "golden-paths" });
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
