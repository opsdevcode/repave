/**
 * Library browse: family chips + shared catalog search. Loaded only from library.html.
 */
import { initCatalogCardMotion, initCatalogSearch } from "./repave-catalog.mjs";

function selectedFamily(root) {
  return (root && root.getAttribute("data-active-family")) || "";
}

function setFamily(root, chips, family) {
  if (!root) {
    return;
  }
  root.setAttribute("data-active-family", family);
  chips.forEach((chip) => {
    const active = (chip.getAttribute("data-library-family") || "") === family;
    chip.classList.toggle("is-active", active);
    chip.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function familyFromLocation(allowed) {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("family") || "";
  if (allowed.has(fromQuery)) {
    return fromQuery;
  }
  const hash = (window.location.hash || "").replace(/^#library-/, "");
  if (allowed.has(hash)) {
    return hash;
  }
  return "";
}

function boot() {
  const chipRoot = document.querySelector("[data-library-families]");
  const chips = chipRoot
    ? Array.from(chipRoot.querySelectorAll("[data-library-family]"))
    : [];
  const allowed = new Set(
    chips
      .map((chip) => chip.getAttribute("data-library-family") || "")
      .filter(Boolean),
  );
  setFamily(chipRoot, chips, familyFromLocation(allowed));

  const catalog = initCatalogSearch({
    extraConstraintActive: () => Boolean(selectedFamily(chipRoot)),
    extraSearchParams: () => ({ family: selectedFamily(chipRoot) }),
    isGroupAllowed: (group) => {
      const family = selectedFamily(chipRoot);
      return !family || group.getAttribute("data-catalog-group") === family;
    },
  });

  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const next = chip.getAttribute("data-library-family") || "";
      const current = selectedFamily(chipRoot);
      setFamily(chipRoot, chips, next === current ? "" : next);
      catalog.applyFilter();
    });
  });

  initCatalogCardMotion();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
