/**
 * Library drawer search. Loaded only from a family shelf on library.html.
 */
import { initCatalogSearch } from "./repave-catalog.mjs";

function boot() {
  initCatalogSearch();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
