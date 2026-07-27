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
    toast.classList.remove("toast--show");
    void toast.offsetWidth;
    toast.classList.add("toast--show");
    if (showToast._timer) {
      clearTimeout(showToast._timer);
    }
    showToast._timer = setTimeout(function () {
      toast.classList.remove("toast--show");
      toast.hidden = true;
    }, 2400);
  }

  function setBusyOverlay(active, label) {
    var overlay = document.getElementById("repave-busy-overlay");
    var labelNode = document.getElementById("repave-busy-label");
    if (!overlay) {
      return;
    }
    if (labelNode && label) {
      labelNode.textContent = label;
    }
    overlay.hidden = !active;
    document.body.classList.toggle("repave-busy", active);
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
    var backstageTab = explorer.querySelector("[data-backstage-file]");
    if (backstageTab && document.querySelector("[data-backstage-highlight]")) {
      backstageTab.click();
    }
  }

  function initBusyForms() {
    document.querySelectorAll("[data-repave-busy-form]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (event.defaultPrevented) {
          return;
        }
        var btn =
          form.querySelector("[data-dry-run-run]:not([hidden])") ||
          form.querySelector("[data-stepper-submit]:not([hidden])") ||
          form.querySelector('button[type="submit"]');
        if (!btn || btn.disabled) {
          return;
        }
        var busyLabel = form.getAttribute("data-busy-label") || "Working…";
        var stages = (form.getAttribute("data-busy-stages") || "")
          .split("|")
          .map(function (s) {
            return s.trim();
          })
          .filter(Boolean);
        var stageLabel = stages.length ? stages[0] : busyLabel;
        var originalLabel = btn.textContent;
        window.setTimeout(function () {
          if (event.defaultPrevented) {
            return;
          }
          btn.disabled = true;
          btn.classList.add("btn--busy");
          btn.dataset.repaveOriginalLabel = originalLabel;
          btn.textContent = stages.length ? stages[0] : busyLabel;
          setBusyOverlay(true, stageLabel);
          if (stages.length > 1) {
            var stageIndex = 0;
            if (form._repaveStageTimer) {
              clearInterval(form._repaveStageTimer);
            }
            form._repaveStageTimer = setInterval(function () {
              stageIndex = (stageIndex + 1) % stages.length;
              btn.textContent = stages[stageIndex];
              setBusyOverlay(true, stages[stageIndex]);
            }, 2200);
          }
        }, 0);
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

  function initFormStepper() {
    var form = document.querySelector("[data-form-stepper]");
    if (!form) {
      return;
    }
    var steps = form.querySelectorAll("[data-form-step]");
    var navSteps = form.querySelectorAll("[data-stepper-index]");
    var backBtn = form.querySelector("[data-stepper-back]");
    var nextBtn = form.querySelector("[data-stepper-next]");
    var submitBtn = form.querySelector("[data-stepper-submit]");
    var dryRunBtn = form.querySelector("[data-dry-run-run]");
    var drySubmitBtn = form.querySelector("[data-dry-run-submit]");
    var dryRunForceField = form.querySelector("[data-dry-run-force]");
    var current = 0;
    var maxStep = parseInt(form.getAttribute("data-form-stepper-max") || "2", 10);
    if (Number.isNaN(maxStep)) {
      maxStep = 2;
    }

    function isFieldVisible(field) {
      if (!field || field.disabled) {
        return false;
      }
      if (field.type === "hidden") {
        return false;
      }
      var node = field;
      while (node && node !== form) {
        if (node.hidden) {
          return false;
        }
        node = node.parentElement;
      }
      return true;
    }

    function validateStep(stepIndex, includeHidden) {
      if (typeof form.reportValidity !== "function") {
        return true;
      }
      var stepRoots = form.querySelectorAll('[data-form-step="' + stepIndex + '"]');
      var fields = [];
      stepRoots.forEach(function (root) {
        root.querySelectorAll("input, select, textarea").forEach(function (field) {
          fields.push(field);
        });
      });
      for (var i = 0; i < fields.length; i += 1) {
        if (!includeHidden && !isFieldVisible(fields[i])) {
          continue;
        }
        if (fields[i].disabled) {
          continue;
        }
        if (fields[i].type === "hidden") {
          continue;
        }
        if (!fields[i].checkValidity()) {
          fields[i].reportValidity();
          return false;
        }
      }
      return true;
    }

    function validateStepsThroughDelivery() {
      var step;
      for (step = 0; step < maxStep; step += 1) {
        if (!validateStep(step, true)) {
          current = step;
          applyStep();
          return false;
        }
      }
      return true;
    }

    function dispatchPreSubmit() {
      form.dispatchEvent(
        new CustomEvent("repave:stepper-pre-submit", {
          bubbles: true,
          cancelable: false,
        })
      );
    }

    function setPlanSubmitMode(planMode) {
      if (dryRunForceField) {
        dryRunForceField.disabled = !planMode;
      }
      form.querySelectorAll('input[name="dry_run"][type="radio"]').forEach(function (radio) {
        radio.disabled = planMode;
      });
    }

    function deliveryWantsPlan() {
      var planRadio = form.querySelector('input[name="dry_run"][type="radio"][value="true"]');
      return !planRadio || planRadio.checked;
    }

    function submitViaDryRunControl() {
      var submitter = drySubmitBtn || submitBtn;
      if (!submitter) {
        return;
      }
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit(submitter);
      } else {
        submitter.click();
      }
    }

    function runStepperSubmitPipeline(formEvent) {
      dispatchPreSubmit();
      var allowed = form.dispatchEvent(
        new CustomEvent("repave:stepper-will-submit", {
          bubbles: true,
          cancelable: true,
        })
      );
      if (!allowed) {
        if (formEvent) {
          formEvent.preventDefault();
        }
        return false;
      }
      if (!validateStepsThroughDelivery()) {
        if (formEvent) {
          formEvent.preventDefault();
        }
        return false;
      }
      return true;
    }

    function forcePlanDryRun() {
      form.querySelectorAll('input[name="dry_run"][type="radio"]').forEach(function (radio) {
        radio.checked = radio.value === "true";
      });
      setPlanSubmitMode(true);
    }

    function runDryRunFromForm() {
      if (!runStepperSubmitPipeline(null)) {
        return;
      }
      forcePlanDryRun();
      submitViaDryRunControl();
    }

    function applyStep() {
      steps.forEach(function (node) {
        var step = Number(node.getAttribute("data-form-step"));
        node.hidden = step !== current;
      });
      navSteps.forEach(function (node) {
        var index = Number(node.getAttribute("data-stepper-index"));
        node.classList.toggle("is-active", index === current);
        node.setAttribute("aria-current", index === current ? "step" : "false");
      });
      if (backBtn) {
        backBtn.hidden = current === 0;
      }
      if (nextBtn) {
        nextBtn.hidden = current >= maxStep;
      }
      if (submitBtn) {
        submitBtn.hidden = current !== maxStep;
      }
      var stickyActions = form.querySelector(".form-actions--sticky");
      if (stickyActions) {
        stickyActions.classList.toggle("form-actions--stepper-final", current === maxStep);
      }
      form.dispatchEvent(
        new CustomEvent("repave:stepper-change", {
          detail: { step: current, maxStep: maxStep },
        })
      );
      form.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    if (dryRunBtn) {
      dryRunBtn.addEventListener("click", runDryRunFromForm);
    }
    form.addEventListener(
      "submit",
      function (event) {
        if (!runStepperSubmitPipeline(event)) {
          return;
        }
        var submitter = event.submitter;
        var viaDryRunControl =
          submitter &&
          (submitter === drySubmitBtn ||
            submitter.getAttribute("data-dry-run-submit") !== null ||
            submitter.getAttribute("data-dry-run-run") !== null);
        if (viaDryRunControl || current !== maxStep) {
          setPlanSubmitMode(true);
        } else {
          setPlanSubmitMode(deliveryWantsPlan());
        }
      },
      true
    );
    if (backBtn) {
      backBtn.addEventListener("click", function () {
        current = Math.max(0, current - 1);
        applyStep();
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", function () {
        if (!validateStep(current)) {
          return;
        }
        var willAdvance = new CustomEvent("repave:stepper-will-advance", {
          detail: { fromStep: current, toStep: Math.min(maxStep, current + 1) },
          cancelable: true,
        });
        if (!form.dispatchEvent(willAdvance)) {
          return;
        }
        current = Math.min(maxStep, current + 1);
        applyStep();
      });
    }
    applyStep();
  }

  function initHomeQuicknav() {
    var layout = document.querySelector("[data-home-layout]");
    var quicknav = document.querySelector("[data-home-quicknav]");
    if (!layout || !quicknav) {
      return;
    }

    var toggle = quicknav.querySelector("[data-quicknav-toggle]");
    var toggleText = toggle ? toggle.querySelector(".home-quicknav__toggle-text") : null;
    var COLLAPSE_KEY = "repave:quicknavCollapsed";

    function setCollapsed(collapsed) {
      layout.classList.toggle("home-layout--quicknav-collapsed", collapsed);
      if (toggle) {
        toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
        toggle.setAttribute(
          "aria-label",
          collapsed ? "Expand quick menu" : "Collapse quick menu"
        );
      }
      if (toggleText) {
        toggleText.textContent = collapsed ? "Expand" : "Collapse";
      }
      try {
        localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
      } catch (_err) {
        /* ignore */
      }
    }

    if (toggle) {
      var stored = null;
      try {
        stored = localStorage.getItem(COLLAPSE_KEY);
      } catch (_err) {
        /* ignore */
      }
      if (stored === "1") {
        setCollapsed(true);
      }
      toggle.addEventListener("click", function () {
        setCollapsed(!layout.classList.contains("home-layout--quicknav-collapsed"));
      });
    }

    quicknav.querySelectorAll(".home-quicknav__family").forEach(function (link) {
      link.addEventListener("click", function (event) {
        event.stopPropagation();
      });
    });

    var GROUPS_KEY = "repave:quicknavGroupsOpen";
    var groupDetails = quicknav.querySelectorAll("[data-quicknav-group]");
    if (groupDetails.length) {
      try {
        var storedGroups = localStorage.getItem(GROUPS_KEY);
        if (storedGroups) {
          var openGroups = JSON.parse(storedGroups);
          groupDetails.forEach(function (node) {
            var id = node.getAttribute("data-quicknav-group");
            if (id && openGroups[id]) {
              node.setAttribute("open", "");
            }
          });
        }
      } catch (_err) {
        /* ignore */
      }
      groupDetails.forEach(function (node) {
        node.addEventListener("toggle", function () {
          var state = {};
          groupDetails.forEach(function (other) {
            var id = other.getAttribute("data-quicknav-group");
            if (id && other.open) {
              state[id] = true;
            }
          });
          try {
            localStorage.setItem(GROUPS_KEY, JSON.stringify(state));
          } catch (_err2) {
            /* ignore */
          }
        });
      });
    }

    var sectionLinks = quicknav.querySelectorAll("[data-quicknav-section]");
    if (!sectionLinks.length) {
      return;
    }
    var sectionIds = [];
    sectionLinks.forEach(function (link) {
      var id = link.getAttribute("data-quicknav-section");
      if (id && sectionIds.indexOf(id) === -1) {
        sectionIds.push(id);
      }
    });
    var sections = sectionIds
      .map(function (id) {
        return document.getElementById(id);
      })
      .filter(Boolean);
    if (!sections.length) {
      return;
    }

    function openQuicknavGroupForSection(sectionId) {
      if (!sectionId || sectionId.indexOf("catalog-") !== 0) {
        return;
      }
      var family = sectionId.replace("catalog-", "");
      var details = quicknav.querySelector('[data-quicknav-group="' + family + '"]');
      if (details && !details.open) {
        details.setAttribute("open", "");
      }
    }

    function setActive(id) {
      sectionLinks.forEach(function (link) {
        var match = link.getAttribute("data-quicknav-section") === id;
        link.classList.toggle("is-active", match);
      });
      openQuicknavGroupForSection(id);
    }

    if ("IntersectionObserver" in window) {
      var visible = new Map();
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            visible.set(entry.target.id, entry.intersectionRatio);
          });
          var bestId = null;
          var bestRatio = 0;
          visible.forEach(function (ratio, targetId) {
            if (ratio >= bestRatio) {
              bestRatio = ratio;
              bestId = targetId;
            }
          });
          if (bestId) {
            setActive(bestId);
          }
        },
        {
          root: null,
          rootMargin: "-20% 0px -55% 0px",
          threshold: [0, 0.1, 0.25, 0.5],
        }
      );
      sections.forEach(function (section) {
        observer.observe(section);
      });
    }

    sectionLinks.forEach(function (link) {
      link.addEventListener("click", function () {
        var id = link.getAttribute("data-quicknav-section");
        if (id) {
          setActive(id);
        }
      });
    });
  }

  function initHomeResumeChip() {
    var mount = document.getElementById("home-resume-chip");
    if (!mount) {
      return;
    }
    var run = readLastRun();
    if (!run || !run.blueprint) {
      mount.hidden = true;
      mount.innerHTML = "";
      return;
    }
    var href = "/blueprints/" + encodeURIComponent(run.blueprint);
    mount.innerHTML =
      '<a class="btn btn--secondary" href="' +
      href +
      '">Resume <code>' +
      run.blueprint +
      "</code></a>";
    mount.hidden = false;
  }

  function initCatalogSearch() {
    var root = document.querySelector("[data-catalog-search]");
    var input = document.querySelector("[data-catalog-search-input]");
    if (!root || !input) {
      return;
    }
    var meta = root.querySelector("[data-catalog-search-meta]");
    var emptyState = document.getElementById("catalog-search-empty");
    var cards = document.querySelectorAll("[data-catalog-card]");
    var groups = document.querySelectorAll("[data-catalog-group]");
    var quickPaths = document.querySelectorAll("[data-quicknav-path]");

    function normalize(value) {
      return (value || "").toLowerCase().trim();
    }

    function applyFilter() {
      var query = normalize(input.value);
      var terms = query ? query.split(/\s+/).filter(Boolean) : [];
      var visibleCards = 0;

      cards.forEach(function (card) {
        var haystack = normalize(card.getAttribute("data-search-text"));
        var match =
          terms.length === 0 || terms.every(function (term) {
            return haystack.indexOf(term) !== -1;
          });
        card.hidden = !match;
        if (match) {
          visibleCards += 1;
        }
      });

      groups.forEach(function (group) {
        var sectionCards = group.querySelectorAll("[data-catalog-card]");
        var anyVisible = false;
        sectionCards.forEach(function (card) {
          if (!card.hidden) {
            anyVisible = true;
          }
        });
        group.hidden = !anyVisible && terms.length > 0;
      });

      quickPaths.forEach(function (row) {
        var haystack = normalize(row.getAttribute("data-search-text"));
        var match =
          terms.length === 0 || terms.every(function (term) {
            return haystack.indexOf(term) !== -1;
          });
        row.hidden = !match;
      });

      if (meta) {
        if (terms.length === 0) {
          meta.hidden = true;
        } else {
          meta.hidden = false;
          meta.textContent =
            visibleCards === 1
              ? "1 golden path matches"
              : visibleCards + " golden paths match";
        }
      }
      if (emptyState) {
        emptyState.hidden = !(terms.length > 0 && visibleCards === 0);
      }
    }

    input.addEventListener("input", applyFilter);
    applyFilter();
  }

  function initGateDashboard() {
    var dashboard = document.querySelector("[data-gate-dashboard]");
    if (!dashboard) {
      return;
    }
    var rows = dashboard.querySelectorAll("[data-gate-row]");
    var jumpBtn = dashboard.querySelector("[data-gate-jump-fail]");
    var copyBtn = dashboard.querySelector("[data-copy-result-summary]");

    function applyGateFilter(value) {
      dashboard.querySelectorAll(".gate-filter").forEach(function (chip) {
        chip.classList.toggle(
          "is-active",
          chip.getAttribute("data-gate-filter-value") === value
        );
      });
      rows.forEach(function (row) {
        var status = row.getAttribute("data-gate-status");
        var show = value === "all" || status === value;
        row.hidden = !show;
      });
    }

    dashboard.querySelectorAll(".gate-filter").forEach(function (chip) {
      chip.addEventListener("click", function () {
        applyGateFilter(chip.getAttribute("data-gate-filter-value") || "all");
      });
    });

    if (jumpBtn) {
      jumpBtn.addEventListener("click", function () {
        var target = dashboard.querySelector('[data-gate-status="fail"]');
        if (!target) {
          return;
        }
        applyGateFilter("fail");
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        var details = target.querySelector("details");
        if (details) {
          details.open = true;
        }
      });
    }

    if (copyBtn) {
      copyBtn.addEventListener("click", function () {
        var node = document.getElementById("result-summary-json");
        if (!node) {
          return;
        }
        var text = node.textContent || "";
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () {
            showToast("Result summary copied");
          });
        }
      });
    }
  }

  function initFormDryRun() {
    document.querySelectorAll("[data-repave-busy-form]").forEach(function (form) {
      if (form.hasAttribute("data-form-stepper")) {
        return;
      }
      var dryRunBtn = form.querySelector("[data-dry-run-run]");
      var drySubmit = form.querySelector("[data-dry-run-submit]");
      var dryForce = form.querySelector("[data-dry-run-force]");
      if (!dryRunBtn || !drySubmit) {
        return;
      }

      dryRunBtn.addEventListener("click", function () {
        form.dispatchEvent(
          new CustomEvent("repave:stepper-pre-submit", { bubbles: true, cancelable: false })
        );
        var allowed = form.dispatchEvent(
          new CustomEvent("repave:stepper-will-submit", { bubbles: true, cancelable: true })
        );
        if (!allowed) {
          return;
        }
        form.querySelectorAll('input[name="dry_run"][type="radio"]').forEach(function (radio) {
          if (radio.value === "true") {
            radio.checked = true;
          }
        });
        if (dryForce) {
          dryForce.disabled = false;
        }
        form.querySelectorAll('input[name="dry_run"][type="radio"]').forEach(function (radio) {
          radio.disabled = true;
        });
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit(drySubmit);
        } else {
          drySubmit.click();
        }
      });
    });
  }

  function initFormDraft() {
    var form = document.querySelector("[data-repave-form-draft]");
    if (!form) {
      return;
    }
    var blueprintId = form.getAttribute("data-blueprint-id") || "default";
    var storageKey = "repave:draft:" + blueprintId;
    var banner = document.getElementById("form-draft-banner");
    var saveTimer = null;

    function serializeForm() {
      var data = {};
      form.querySelectorAll("input, select, textarea").forEach(function (field) {
        if (!field.name || field.type === "file") {
          return;
        }
        if (field.type === "checkbox") {
          data[field.name] = field.checked;
        } else if (field.type === "radio") {
          if (field.checked) {
            data[field.name] = field.value;
          }
        } else {
          data[field.name] = field.value;
        }
      });
      return data;
    }

    function applyDraft(data) {
      Object.keys(data).forEach(function (name) {
        var fields = form.querySelectorAll('[name="' + name + '"]');
        fields.forEach(function (field) {
          if (field.type === "checkbox") {
            field.checked = Boolean(data[name]);
          } else if (field.type === "radio") {
            field.checked = field.value === String(data[name]);
          } else {
            field.value = data[name];
          }
          field.dispatchEvent(new Event("change", { bubbles: true }));
        });
      });
    }

    function saveDraft() {
      try {
        localStorage.setItem(storageKey, JSON.stringify(serializeForm()));
      } catch (_err) {
        /* ignore */
      }
    }

    function scheduleSave() {
      if (saveTimer) {
        clearTimeout(saveTimer);
      }
      saveTimer = setTimeout(saveDraft, 450);
    }

    try {
      var raw = localStorage.getItem(storageKey);
      if (raw && banner) {
        banner.hidden = false;
        banner.setAttribute("aria-label", "Saved blueprint draft");
        banner.innerHTML =
          '<span class="muted">Saved draft for this blueprint.</span> ' +
          '<button type="button" class="btn btn--ghost btn--sm" data-draft-restore>Restore</button> ' +
          '<button type="button" class="btn btn--ghost btn--sm" data-draft-discard>Discard</button>';
        banner.querySelector("[data-draft-restore]").addEventListener("click", function () {
          try {
            applyDraft(JSON.parse(raw));
            showToast("Draft restored");
          } catch (_err2) {
            /* ignore */
          }
        });
        banner.querySelector("[data-draft-discard]").addEventListener("click", function () {
          try {
            localStorage.removeItem(storageKey);
          } catch (_err3) {
            /* ignore */
          }
          banner.hidden = true;
          banner.innerHTML = "";
          banner.removeAttribute("aria-label");
        });
      }
    } catch (_err4) {
      /* ignore */
    }

    if (banner && banner.hidden) {
      banner.innerHTML = "";
    }

    form.addEventListener("input", scheduleSave);
    form.addEventListener("change", scheduleSave);
    form.addEventListener("submit", function () {
      try {
        localStorage.removeItem(storageKey);
      } catch (_err5) {
        /* ignore */
      }
    });
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
      initHomeResumeChip();
    },
    renderLastRun: function () {
      renderLastRun();
      initHomeResumeChip();
    },
    showToast: showToast,
  };

  document.addEventListener("DOMContentLoaded", function () {
    renderLastRun();
    initHomeResumeChip();
    initCopyButtons();
    initFileExplorer();
    initBusyForms();
    initFormStepper();
    initFormDryRun();
    initHomeQuicknav();
    initCatalogSearch();
    initGateDashboard();
    initFormDraft();
  });
})();
