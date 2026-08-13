/**
 * Library index motion + family-shelf search. Loaded from library.html.
 */
import { initCatalogSearch, initLibraryDrawerMotion } from "./repave-catalog.mjs";

function boot() {
  initLibraryDrawerMotion();
  initCatalogSearch();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
