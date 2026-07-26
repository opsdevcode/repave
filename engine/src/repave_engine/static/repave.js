(function () {
  var STORAGE_KEY = "repave:lastRun";

  function readLastRun() {
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return null;
      }
      return JSON.parse(raw);
    } catch (_err) {
      return null;
    }
  }

  function formatRelativeTime(iso) {
    var then = Date.parse(iso);
    if (Number.isNaN(then)) {
      return "";
    }
    var seconds = Math.round((Date.now() - then) / 1000);
    if (seconds < 60) {
      return "just now";
    }
    var minutes = Math.round(seconds / 60);
    if (minutes < 60) {
      return minutes + " min ago";
    }
    var hours = Math.round(minutes / 60);
    if (hours < 48) {
      return hours + " h ago";
    }
    return new Date(then).toLocaleString();
  }

  function showToast(message) {
    var toast = document.getElementById("repave-toast");
    if (!toast) {
      return;
    }
    toast.textContent = message;
    toast.hidden = false;
    if (showToast._timer) {
      clearTimeout(showToast._timer);
    }
    showToast._timer = setTimeout(function () {
      toast.hidden = true;
    }, 2400);
  }

  function initCopyButtons() {
    document.querySelectorAll("[data-copy-target]").forEach(function (button) {
      if (button.dataset.repaveCopyBound) {
        return;
      }
      button.dataset.repaveCopyBound = "1";
      var defaultLabel = button.textContent.trim() || "Copy";
      button.addEventListener("click", function () {
        var selector = button.getAttribute("data-copy-target");
        var node = selector ? document.querySelector(selector) : null;
        if (!node) {
          return;
        }
        var text = node.textContent || "";
        var doneLabel = button.getAttribute("data-copy-done") || "Copied";

        function onCopied() {
          button.textContent = doneLabel;
          showToast("Copied to clipboard");
          setTimeout(function () {
            button.textContent = defaultLabel;
          }, 2000);
        }

        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(onCopied).catch(function () {});
        }
      });
    });
  }

  function initFileExplorer() {
    var explorer = document.querySelector("[data-file-explorer]");
    if (!explorer) {
      return;
    }
    var tabs = explorer.querySelectorAll(".file-explorer__tab");
    var panes = explorer.querySelectorAll(".file-explorer__pane");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var index = tab.getAttribute("data-file-index");
        tabs.forEach(function (other) {
          other.classList.toggle("is-active", other === tab);
          other.setAttribute("aria-selected", other === tab ? "true" : "false");
        });
        panes.forEach(function (pane) {
          var active = pane.getAttribute("data-file-pane") === index;
          pane.classList.toggle("is-active", active);
          pane.hidden = !active;
        });
      });
    });
  }

  function initBusyForms() {
    document.querySelectorAll("[data-repave-busy-form]").forEach(function (form) {
      form.addEventListener("submit", function () {
        var btn = form.querySelector('button[type="submit"]');
        if (!btn || btn.disabled) {
          return;
        }
        btn.disabled = true;
        btn.classList.add("btn--busy");
        var busyLabel = form.getAttribute("data-busy-label") || "Working…";
        btn.dataset.repaveOriginalLabel = btn.textContent;
        btn.textContent = busyLabel;
      });
    });
  }

  function dismissLastRun(event) {
    event.preventDefault();
    event.stopPropagation();
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch (_err) {
      /* ignore */
    }
    renderLastRun();
  }

  function renderLastRun() {
    var mount = document.getElementById("last-run-snippet");
    if (!mount) {
      return;
    }
    var run = readLastRun();
    if (!run || !run.blueprint) {
      mount.hidden = true;
      mount.innerHTML = "";
      return;
    }
    var outcome = run.outcome === "failed" ? "failed" : "passed";
    var badgeClass = outcome === "failed" ? "badge--fail" : "badge--pass";
    var mode = run.dryRun ? "dry-run" : "published";
    var when = formatRelativeTime(run.timestamp);
    var blueprintUrl = "/blueprints/" + encodeURIComponent(run.blueprint);
    mount.innerHTML =
      '<div class="last-run-snippet__inner">' +
      '<span class="muted">Last run in this browser</span> ' +
      '<a href="' +
      blueprintUrl +
      '"><code>' +
      run.blueprint +
      "</code></a> " +
      '<span class="badge ' +
      badgeClass +
      '">' +
      outcome.toUpperCase() +
      "</span> " +
      '<span class="muted">' +
      mode +
      (when ? " · " + when : "") +
      "</span> " +
      '<button type="button" class="btn btn--ghost btn--sm last-run-snippet__dismiss" aria-label="Dismiss last run">' +
      "Dismiss" +
      "</button>" +
      "</div>";
    mount.hidden = false;
    var dismiss = mount.querySelector(".last-run-snippet__dismiss");
    if (dismiss) {
      dismiss.addEventListener("click", dismissLastRun);
    }
  }

  window.repavePortal = {
    saveLastRun: function (payload) {
      try {
        sessionStorage.setItem(
          STORAGE_KEY,
          JSON.stringify(
            Object.assign({}, payload, { timestamp: new Date().toISOString() })
          )
        );
      } catch (_err) {
        /* ignore quota / private mode */
      }
      renderLastRun();
    },
    renderLastRun: renderLastRun,
    showToast: showToast,
  };

  document.addEventListener("DOMContentLoaded", function () {
    renderLastRun();
    initCopyButtons();
    initFileExplorer();
    initBusyForms();
  });
})();
