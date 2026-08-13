/**
 * Platform motion (native ES module, no bundler, no third-party scripts).
 * Spring pointer faces, magnetic CTAs, atmosphere parallax, catalog glare.
 * Loaded from base.html on every page. Respects reduced motion and coarse pointers.
 */

const FACE_SELECTOR = [
  "[data-motion-face]",
  "[data-library-drawer]",
  ".home-catalog [data-catalog-card]",
  ".catalog-inventory__item[data-catalog-card]",
].join(", ");
const MAGNETIC_SELECTOR = [
  ".btn--primary",
  ".btn--secondary",
  ".btn--ghost",
  ".preset-chip",
  ".shell__nav--primary > a",
  ".home-quick a",
].join(", ");
const SKIP_FACE = ".library-shelf__item, .command-palette, [disabled], [aria-disabled='true']";
const SPRING = 0.16;
const SETTLE = 0.05;
const FACE_TILT = 11;
const FACE_LIFT = 14;
const MAGNETIC_PULL = 8;
const ATMOSPHERE_RANGE = 18;
const NEIGHBOR_RADIUS = 320;
const NEIGHBOR_PUSH = 12;

export function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function prefersFinePointer() {
  return window.matchMedia("(hover: hover) and (pointer: fine)").matches;
}

function restState() {
  return { rx: 0, ry: 0, tx: 0, ty: 0, tz: 0, sx: 50, sy: 40, glare: -40 };
}

function lerp(current, target, amount) {
  return current + (target - current) * amount;
}

function nearRest(state) {
  return (
    Math.abs(state.rx) < SETTLE &&
    Math.abs(state.ry) < SETTLE &&
    Math.abs(state.tx) < SETTLE &&
    Math.abs(state.ty) < SETTLE &&
    Math.abs(state.tz) < SETTLE
  );
}

function applyFace(entry) {
  const { el, kind, current } = entry;
  el.style.setProperty("--spot-x", current.sx.toFixed(1) + "%");
  el.style.setProperty("--spot-y", current.sy.toFixed(1) + "%");
  el.style.setProperty("--glare-x", current.glare.toFixed(1) + "%");
  if (kind === "magnetic") {
    el.style.transform =
      "translate3d(" + current.tx.toFixed(2) + "px, " + current.ty.toFixed(2) + "px, 0)";
  } else {
    el.style.transform =
      "perspective(920px) rotateX(" +
      current.rx.toFixed(2) +
      "deg) rotateY(" +
      current.ry.toFixed(2) +
      "deg) translate3d(" +
      current.tx.toFixed(2) +
      "px, " +
      current.ty.toFixed(2) +
      "px, " +
      current.tz.toFixed(2) +
      "px)";
  }
  const nx = (current.sx / 100 - 0.5) * 2;
  const ny = (current.sy / 100 - 0.5) * 2;
  el.querySelectorAll("[data-motion-depth]").forEach((layer) => {
    const depth = Number(layer.getAttribute("data-motion-depth")) || 0.4;
    layer.style.transform =
      "translate3d(" + (nx * 10 * depth).toFixed(2) + "px, " + (ny * 8 * depth).toFixed(2) + "px, 0)";
  });
}

function clearFace(el) {
  el.style.transform = "";
  ["--spot-x", "--spot-y", "--glare-x"].forEach((name) => {
    el.style.removeProperty(name);
  });
  el.querySelectorAll("[data-motion-depth]").forEach((layer) => {
    layer.style.transform = "";
  });
}

function pointerMetrics(el, clientX, clientY) {
  const rect = el.getBoundingClientRect();
  const width = Math.max(rect.width, 1);
  const height = Math.max(rect.height, 1);
  const px = Math.min(1, Math.max(0, (clientX - rect.left) / width));
  const py = Math.min(1, Math.max(0, (clientY - rect.top) / height));
  return { px, py, nx: px - 0.5, ny: py - 0.5 };
}

function spawnRipple(el, clientX, clientY) {
  const rect = el.getBoundingClientRect();
  const mark = document.createElement("span");
  mark.className = "motion-ripple";
  mark.style.left = clientX - rect.left + "px";
  mark.style.top = clientY - rect.top + "px";
  el.append(mark);
  mark.addEventListener("animationend", () => {
    mark.remove();
  });
}

const bound = new WeakSet();
const nodes = new Map();
let raf = 0;
const atmosphere = { x: 0, y: 0, tx: 0, ty: 0 };
let atmosphereListening = false;

function ensure(el, kind) {
  let entry = nodes.get(el);
  if (!entry) {
    entry = {
      el,
      kind,
      current: restState(),
      target: restState(),
      neighborTx: 0,
      neighborTy: 0,
      live: false,
    };
    nodes.set(el, entry);
  }
  return entry;
}

function aimFace(entry, clientX, clientY) {
  const { px, py, nx, ny } = pointerMetrics(entry.el, clientX, clientY);
  if (entry.kind === "magnetic") {
    entry.target = {
      rx: 0,
      ry: 0,
      tx: nx * MAGNETIC_PULL * 2,
      ty: ny * MAGNETIC_PULL * 2,
      tz: 0,
      sx: px * 100,
      sy: py * 100,
      glare: px * 80 - 40,
    };
    return;
  }
  entry.target = {
    rx: -ny * FACE_TILT,
    ry: nx * FACE_TILT,
    tx: nx * 6,
    ty: ny * 5 - 6,
    tz: FACE_LIFT,
    sx: px * 100,
    sy: py * 100,
    glare: px * 90 - 45,
  };
}

function resetNeighbors() {
  nodes.forEach((entry) => {
    entry.neighborTx = 0;
    entry.neighborTy = 0;
  });
}

function pushNeighbors(liveEl) {
  resetNeighbors();
  const pack = liveEl.closest(".catalog-inventory__items, .library-drawers");
  if (!pack) {
    return;
  }
  const liveRect = liveEl.getBoundingClientRect();
  const cx = liveRect.left + liveRect.width / 2;
  const cy = liveRect.top + liveRect.height / 2;
  pack.querySelectorAll(".motion-face").forEach((sib) => {
    if (sib === liveEl) {
      return;
    }
    const entry = nodes.get(sib);
    if (!entry || entry.live) {
      return;
    }
    const rect = sib.getBoundingClientRect();
    const sx = rect.left + rect.width / 2 - cx;
    const sy = rect.top + rect.height / 2 - cy;
    const dist = Math.hypot(sx, sy) || 1;
    const falloff = Math.max(0, 1 - dist / NEIGHBOR_RADIUS);
    if (falloff <= 0) {
      return;
    }
    const push = falloff * NEIGHBOR_PUSH;
    entry.neighborTx = (sx / dist) * push;
    entry.neighborTy = (sy / dist) * push;
  });
}

function tick() {
  raf = 0;
  let busy = false;
  atmosphere.x = lerp(atmosphere.x, atmosphere.tx, SPRING);
  atmosphere.y = lerp(atmosphere.y, atmosphere.ty, SPRING);
  if (Math.abs(atmosphere.x) > SETTLE || Math.abs(atmosphere.y) > SETTLE) {
    busy = true;
  }
  const shell = document.querySelector(".shell");
  if (shell) {
    shell.style.setProperty("--atm-x", atmosphere.x.toFixed(2) + "px");
    shell.style.setProperty("--atm-y", atmosphere.y.toFixed(2) + "px");
  }

  nodes.forEach((entry) => {
    const { current, target } = entry;
    const aimTx = target.tx + entry.neighborTx;
    const aimTy = target.ty + entry.neighborTy;
    current.rx = lerp(current.rx, target.rx, SPRING);
    current.ry = lerp(current.ry, target.ry, SPRING);
    current.tx = lerp(current.tx, aimTx, SPRING);
    current.ty = lerp(current.ty, aimTy, SPRING);
    current.tz = lerp(current.tz, target.tz, SPRING);
    current.sx = lerp(current.sx, target.sx, SPRING);
    current.sy = lerp(current.sy, target.sy, SPRING);
    current.glare = lerp(current.glare, target.glare, SPRING);
    applyFace(entry);
    if (entry.live || !nearRest(current)) {
      busy = true;
    } else if (!entry.live) {
      clearFace(entry.el);
    }
  });

  if (busy) {
    raf = window.requestAnimationFrame(tick);
  }
}

function kick() {
  if (!raf) {
    raf = window.requestAnimationFrame(tick);
  }
}

function bind(el, kind) {
  if (bound.has(el) || el.closest(SKIP_FACE)) {
    return;
  }
  bound.add(el);
  const entry = ensure(el, kind);
  el.classList.add("motion-face");
  if (kind === "magnetic") {
    el.classList.add("motion-face--magnetic");
  }
  el.addEventListener("pointerenter", (event) => {
    entry.live = true;
    el.classList.add("is-live");
    aimFace(entry, event.clientX, event.clientY);
    if (kind === "face") {
      pushNeighbors(el);
    }
    kick();
  });
  el.addEventListener("pointermove", (event) => {
    aimFace(entry, event.clientX, event.clientY);
    kick();
  });
  el.addEventListener("pointerleave", () => {
    entry.live = false;
    el.classList.remove("is-live");
    entry.target = restState();
    resetNeighbors();
    kick();
  });
  el.addEventListener("pointerdown", (event) => {
    if (kind !== "face") {
      return;
    }
    spawnRipple(el, event.clientX, event.clientY);
  });
}

export function initPointerFaces() {
  if (prefersReducedMotion() || !prefersFinePointer()) {
    return;
  }

  document.querySelectorAll(FACE_SELECTOR).forEach((el) => {
    bind(el, "face");
  });
  document.querySelectorAll(MAGNETIC_SELECTOR).forEach((el) => {
    if ("disabled" in el && el.disabled) {
      return;
    }
    bind(el, "magnetic");
  });

  if (!atmosphereListening) {
    atmosphereListening = true;
    window.addEventListener(
      "pointermove",
      (event) => {
        const nx = event.clientX / Math.max(window.innerWidth, 1) - 0.5;
        const ny = event.clientY / Math.max(window.innerHeight, 1) - 0.5;
        atmosphere.tx = nx * ATMOSPHERE_RANGE;
        atmosphere.ty = ny * ATMOSPHERE_RANGE;
        kick();
      },
      { passive: true },
    );
  }
}

export function initCatalogCardMotion() {
  initPointerFaces();
}

export function initLibraryDrawerMotion() {
  initPointerFaces();
}

function boot() {
  initPointerFaces();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
