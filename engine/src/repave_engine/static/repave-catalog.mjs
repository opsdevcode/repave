/**
 * Shared catalog browse helpers (home + library). No bundler; relative import only.
 */

export function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function prefersFinePointer() {
  return window.matchMedia("(hover: hover) and (pointer: fine)").matches;
}

export function supportsViewTransitions() {
  return (
    typeof document.startViewTransition === "function" && !prefersReducedMotion()
  );
}

export function runWithViewTransition(update) {
  if (!supportsViewTransitions()) {
    update();
    return;
  }
  document.startViewTransition(update);
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

function syncSearchToUrl(query, extraSearchParams) {
  const url = new URL(window.location.href);
  if (query) {
    url.searchParams.set("q", query);
  } else {
    url.searchParams.delete("q");
  }
  const extra = extraSearchParams();
  Object.keys(extra).forEach((key) => {
    const value = extra[key];
    if (value) {
      url.searchParams.set(key, value);
    } else {
      url.searchParams.delete(key);
    }
  });
  const next = url.pathname + url.search + url.hash;
  const current = window.location.pathname + window.location.search + window.location.hash;
  if (next !== current) {
    history.replaceState(null, "", next);
  }
}

export function initCatalogCardMotion() {
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

export function initLibraryDrawerMotion() {
  const drawers = Array.from(document.querySelectorAll("[data-library-drawer]"));
  if (!drawers.length || prefersReducedMotion() || !prefersFinePointer()) {
    return;
  }

  drawers.forEach((drawer) => {
    let frame = 0;
    let pendingX = 0;
    let pendingY = 0;

    function applyPointerFace() {
      frame = 0;
      const rect = drawer.getBoundingClientRect();
      const width = Math.max(rect.width, 1);
      const height = Math.max(rect.height, 1);
      const px = Math.min(1, Math.max(0, (pendingX - rect.left) / width));
      const py = Math.min(1, Math.max(0, (pendingY - rect.top) / height));
      drawer.style.setProperty("--spot-x", (px * 100).toFixed(1) + "%");
      drawer.style.setProperty("--spot-y", (py * 100).toFixed(1) + "%");
      drawer.style.transform =
        "perspective(900px) rotateX(" +
        ((0.5 - py) * 7).toFixed(2) +
        "deg) rotateY(" +
        ((px - 0.5) * 8).toFixed(2) +
        "deg) translate3d(0, -5px, 12px)";
    }

    drawer.addEventListener("pointerenter", (event) => {
      drawer.classList.add("is-live");
      pendingX = event.clientX;
      pendingY = event.clientY;
      applyPointerFace();
    });
    drawer.addEventListener("pointermove", (event) => {
      pendingX = event.clientX;
      pendingY = event.clientY;
      if (frame) {
        return;
      }
      frame = window.requestAnimationFrame(applyPointerFace);
    });
    drawer.addEventListener("pointerleave", () => {
      if (frame) {
        window.cancelAnimationFrame(frame);
        frame = 0;
      }
      drawer.classList.remove("is-live");
      drawer.style.transform = "";
      drawer.style.removeProperty("--spot-x");
      drawer.style.removeProperty("--spot-y");
    });
  });
}

export function initCatalogSearch(options = {}) {
  const extraConstraintActive = options.extraConstraintActive || (() => false);
  const extraSearchParams = options.extraSearchParams || (() => ({}));
  const isGroupAllowed = options.isGroupAllowed || (() => true);
  const isItemAllowed = options.isItemAllowed || (() => true);
  const noun = options.noun || "artifact";
  const scrollTargetId = options.scrollTargetId || "";

  const root = document.querySelector("[data-catalog-search]");
  const input = document.querySelector("[data-catalog-search-input]");
  if (!root || !input) {
    return { applyFilter() {} };
  }
  const meta = root.querySelector("[data-catalog-search-meta]");
  const emptyState = document.getElementById("catalog-search-empty");
  const cards = Array.from(document.querySelectorAll("[data-catalog-card]"));
  const groups = document.querySelectorAll("[data-catalog-group]");
  let activeIndex = -1;

  if (scrollTargetId && window.location.hash === "#" + scrollTargetId) {
    const target = document.getElementById(scrollTargetId);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
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
    const constrained = terms.length > 0 || extraConstraintActive();
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
      match = match && isItemAllowed(card);
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
      group.hidden = !isGroupAllowed(group) || (!anyVisible && constrained);
    });

    if (meta) {
      if (terms.length === 0) {
        meta.hidden = true;
      } else {
        meta.hidden = false;
        meta.textContent =
          visibleCards === 1 ? "1 " + noun + " matches" : visibleCards + " " + noun + "s match";
      }
    }
    if (emptyState) {
      emptyState.hidden = !(constrained && visibleCards === 0);
    }
    activeIndex = -1;
    syncSearchToUrl(query, extraSearchParams);
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
  return { applyFilter: applyFilterWithTransition };
}
