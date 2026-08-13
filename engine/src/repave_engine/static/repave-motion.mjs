/**
 * Platform motion (native ES module, no bundler, no third-party scripts).
 * Spring pointer faces, magnetic CTAs, atmosphere parallax.
 * Loaded from base.html on every page. Respects reduced motion and coarse pointers.
 */

const FACE_SELECTOR = "[data-library-drawer], .catalog-inventory__item[data-catalog-card]";
const MAGNETIC_SELECTOR = ".btn--primary, .shell__nav--primary > a";
const SPRING = 0.18;
const SETTLE = 0.04;
const FACE_TILT = 8;
const FACE_LIFT = 8;
const MAGNETIC_PULL = 7;
const ATMOSPHERE_RANGE = 14;

export function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function prefersFinePointer() {
  return window.matchMedia("(hover: hover) and (pointer: fine)").matches;
}

function restState() {
  return { rx: 0, ry: 0, tx: 0, ty: 0, tz: 0, sx: 50, sy: 40 };
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

function applyFace(el, state) {
  el.style.setProperty("--spot-x", state.sx.toFixed(1) + "%");
  el.style.setProperty("--spot-y", state.sy.toFixed(1) + "%");
  el.style.setProperty("--face-rx", state.rx.toFixed(2) + "deg");
  el.style.setProperty("--face-ry", state.ry.toFixed(2) + "deg");
  el.style.setProperty("--face-tx", state.tx.toFixed(2) + "px");
  el.style.setProperty("--face-ty", state.ty.toFixed(2) + "px");
  el.style.setProperty("--face-tz", state.tz.toFixed(2) + "px");
}

function clearFace(el) {
  [
    "--spot-x",
    "--spot-y",
    "--face-rx",
    "--face-ry",
    "--face-tx",
    "--face-ty",
    "--face-tz",
  ].forEach((name) => {
    el.style.removeProperty(name);
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

let facesAttached = false;

export function initPointerFaces() {
  if (facesAttached || prefersReducedMotion() || !prefersFinePointer()) {
    return;
  }
  facesAttached = true;

  const nodes = new Map();

  function ensure(el, kind) {
    let entry = nodes.get(el);
    if (!entry) {
      entry = { el, kind, current: restState(), target: restState(), live: false };
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
      };
      return;
    }
    entry.target = {
      rx: -ny * FACE_TILT,
      ry: nx * FACE_TILT,
      tx: nx * 4,
      ty: ny * 4 - 4,
      tz: FACE_LIFT,
      sx: px * 100,
      sy: py * 100,
    };
  }

  let raf = 0;
  const atmosphere = { x: 0, y: 0, tx: 0, ty: 0 };

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
      current.rx = lerp(current.rx, target.rx, SPRING);
      current.ry = lerp(current.ry, target.ry, SPRING);
      current.tx = lerp(current.tx, target.tx, SPRING);
      current.ty = lerp(current.ty, target.ty, SPRING);
      current.tz = lerp(current.tz, target.tz, SPRING);
      current.sx = lerp(current.sx, target.sx, SPRING);
      current.sy = lerp(current.sy, target.sy, SPRING);
      applyFace(entry.el, current);
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
    const entry = ensure(el, kind);
    el.classList.add("motion-face");
    if (kind === "magnetic") {
      el.classList.add("motion-face--magnetic");
    }
    el.addEventListener("pointerenter", (event) => {
      entry.live = true;
      el.classList.add("is-live");
      aimFace(entry, event.clientX, event.clientY);
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
      kick();
    });
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
