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

  function initLineageReceiptCopy() {
    document.querySelectorAll("[data-copy-lineage-receipt]").forEach(function (button) {
      if (button.dataset.repaveLineageCopyBound) {
        return;
      }
      button.dataset.repaveLineageCopyBound = "1";
      var defaultLabel = button.textContent.trim() || "Copy";
      button.addEventListener("click", function () {
        var node = document.getElementById("lineage-receipt-data");
        if (!node) {
          return;
        }
        var text = node.textContent.trim();
        if (!text || !navigator.clipboard || !navigator.clipboard.writeText) {
          return;
        }
        navigator.clipboard.writeText(text).then(function () {
          showToast("Lineage receipt copied");
          button.textContent = "Copied";
          setTimeout(function () {
            button.textContent = defaultLabel;
          }, 2000);
        });
      });
    });
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
    document.querySelectorAll("[data-file-explorer]").forEach(function (explorer) {
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
    });
  }

  function initBundleMemberTabs() {
    var root = document.querySelector("[data-bundle-member-tabs]");
    if (!root) {
      return;
    }
    var tabs = root.querySelectorAll("[data-member-tab]");
    var panels = root.querySelectorAll("[data-member-panel]");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var memberId = tab.getAttribute("data-member-tab");
        tabs.forEach(function (other) {
          var active = other === tab;
          other.classList.toggle("is-active", active);
          other.setAttribute("aria-selected", active ? "true" : "false");
        });
        panels.forEach(function (panel) {
          var active = panel.getAttribute("data-member-panel") === memberId;
          panel.classList.toggle("is-active", active);
          panel.hidden = !active;
        });
      });
    });
  }

  function initBundlePreview() {
    var form = document.querySelector("[data-bundle-preview]");
    if (!form) {
      return;
    }
    var configEl = document.getElementById("bundle-preview-templates");
    if (!configEl) {
      return;
    }
    var config;
    try {
      config = JSON.parse(configEl.textContent || "{}");
    } catch (_err) {
      return;
    }
    var githubOrg = config.githubOrg || form.getAttribute("data-github-org") || "example-org";
    var serviceField =
      form.querySelector("[data-bundle-service-name]") || form.querySelector('[name="service_name"]');
    var orgField = form.querySelector('[name="organization"]');

    function slug(value, fallback) {
      var text = (value || "").trim();
      return text || fallback;
    }

    function updatePreview() {
      var serviceName = slug(serviceField && serviceField.value, "example-service");
      var organization = slug(orgField && orgField.value, "platform");
      var items = form.querySelectorAll("[data-preview-member]");
      items.forEach(function (item) {
        var memberId = item.getAttribute("data-preview-member");
        var repoEl = item.querySelector("[data-preview-repo-name]");
        var xrefEl = item.querySelector("[data-preview-cross-ref]");
        var repoName = "";
        if (memberId === "app") {
          repoName = "app-" + serviceName;
        } else if (memberId === "helm") {
          repoName = "helm-" + serviceName;
        } else if (memberId === "dashboards") {
          repoName = "dashboards-" + organization + "-" + serviceName;
        } else if (memberId === "gitops") {
          var envField = form.querySelector('[name="environment"]');
          var environment = slug(envField && envField.value, "dev");
          repoName = "gitops-" + environment + "-" + serviceName;
        } else if (memberId === "monitors") {
          repoName = "monitors-" + organization + "-" + serviceName;
        } else if (memberId === "slo") {
          repoName = "slo-" + organization + "-" + serviceName;
        } else if (memberId === "terraform") {
          var cloudField = form.querySelector('[name="cloud_provider"]');
          var cloud = slug(cloudField && cloudField.value, "aws");
          repoName = "tf-" + cloud + "-" + serviceName;
        }
        if (repoEl && repoName) {
          repoEl.textContent = repoName;
        }
        if (xrefEl) {
          var helmUrl =
            "https://github.com/" + githubOrg + "/helm-" + serviceName;
          var imageRef = "ghcr.io/" + githubOrg + "/app-" + serviceName + ":1.0.0";
          if (memberId === "app") {
            xrefEl.textContent = "Links to Helm chart at " + helmUrl;
          } else if (memberId === "helm") {
            xrefEl.textContent = "Image " + imageRef;
          } else if (memberId === "dashboards") {
            xrefEl.textContent = "Dashboards for service " + serviceName;
          } else if (memberId === "gitops") {
            xrefEl.textContent =
              "Deploys chart " + serviceName + " from " + helmUrl;
          } else if (memberId === "monitors") {
            xrefEl.textContent = "Alerts for " + serviceName + " (runbook linked)";
          } else if (memberId === "slo") {
            var sloField = form.querySelector('[name="slo_target_percent"]');
            var sloTarget = slug(sloField && sloField.value, "99.9");
            xrefEl.textContent =
              "SLO target " + sloTarget + "% for " + serviceName;
          } else if (memberId === "terraform") {
            var cloudProvider = slug(
              form.querySelector('[name="cloud_provider"]') &&
                form.querySelector('[name="cloud_provider"]').value,
              "aws"
            );
            xrefEl.textContent =
              "Terraform module tf-" + cloudProvider + "-" + serviceName;
          }
        }
      });
    }

    if (serviceField) {
      serviceField.addEventListener("input", updatePreview);
    }
    if (orgField) {
      orgField.addEventListener("input", updatePreview);
    }
    form.querySelectorAll('[name="environment"], [name="cloud_provider"], [name="slo_target_percent"]').forEach(
      function (field) {
        field.addEventListener("input", updatePreview);
        field.addEventListener("change", updatePreview);
      }
    );
    updatePreview();
  }

  function initBusyForms() {
    document.querySelectorAll("[data-repave-busy-form]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (event.defaultPrevented) {
          return;
        }
        var streamBox = form.querySelector('input[name="stream"][value="1"]');
        if (streamBox && streamBox.checked) {
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
    var progressEl = form.querySelector("[data-stepper-progress]");
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

    var planPreviewFlag = form.querySelector("[data-plan-preview-flag]");

    function setPlanSubmitMode(planMode) {
      if (dryRunForceField) {
        dryRunForceField.disabled = !planMode;
      }
      if (planPreviewFlag) {
        planPreviewFlag.disabled = !planMode;
        planPreviewFlag.value = planMode ? "1" : "";
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
      if (progressEl) {
        var activeStep = form.querySelector('.form-stepper__step[data-stepper-index="' + current + '"]');
        var labelNode = activeStep ? activeStep.querySelector(".form-stepper__label") : null;
        var label = labelNode ? labelNode.textContent.trim() : "";
        progressEl.textContent =
          "Step " +
          (current + 1) +
          " of " +
          (maxStep + 1) +
          (label ? " · " + label : "");
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

    if (window.location.hash === "#golden-paths") {
      var goldenPaths = document.getElementById("golden-paths");
      if (goldenPaths) {
        goldenPaths.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }

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
          terms.length === 0 ||
          terms.every(function (term) {
            return haystack.indexOf(term) !== -1;
          });
        var row = card.closest("[data-catalog-item]");
        if (row) {
          row.hidden = !match;
        } else {
          card.hidden = !match;
        }
        if (match) {
          visibleCards += 1;
        }
      });

      groups.forEach(function (group) {
        var items = group.querySelectorAll("[data-catalog-item]");
        var anyVisible = false;
        items.forEach(function (item) {
          if (!item.hidden) {
            anyVisible = true;
          }
        });
        group.hidden = !anyVisible && terms.length > 0;
        if (terms.length > 0 && anyVisible && group.tagName === "DETAILS") {
          group.open = true;
        }
      });

      if (meta) {
        if (terms.length === 0) {
          meta.hidden = true;
        } else {
          meta.hidden = false;
          meta.textContent =
            visibleCards === 1
              ? "1 artifact matches"
              : visibleCards + " artifacts match";
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

    var jumpSkipBtn = dashboard.querySelector("[data-gate-jump-skip]");
    if (jumpSkipBtn) {
      jumpSkipBtn.addEventListener("click", function () {
        var target = dashboard.querySelector('[data-gate-status="skip"]');
        if (!target) {
          return;
        }
        applyGateFilter("skip");
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
      var planPreviewFlag = form.querySelector("[data-plan-preview-flag]");
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
        if (planPreviewFlag) {
          planPreviewFlag.disabled = false;
          planPreviewFlag.value = "1";
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

      form.addEventListener(
        "submit",
        function (event) {
          var submitter = event.submitter;
          var viaDryRunControl =
            submitter &&
            (submitter === drySubmit || submitter.getAttribute("data-dry-run-submit") !== null);
          if (viaDryRunControl) {
            if (dryForce) {
              dryForce.disabled = false;
            }
            if (planPreviewFlag) {
              planPreviewFlag.disabled = false;
              planPreviewFlag.value = "1";
            }
            form.querySelectorAll('input[name="dry_run"][type="radio"]').forEach(function (radio) {
              radio.disabled = true;
            });
          } else {
            if (dryForce) {
              dryForce.disabled = true;
            }
            if (planPreviewFlag) {
              planPreviewFlag.disabled = true;
              planPreviewFlag.value = "";
            }
            form.querySelectorAll('input[name="dry_run"][type="radio"]').forEach(function (radio) {
              radio.disabled = false;
            });
          }
        },
        true
      );
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

  function initRunConsole() {
    var root = document.querySelector("[data-run-console]");
    if (!root) {
      return;
    }
    var runId = root.getAttribute("data-run-id");
    var resultUrl = root.getAttribute("data-result-url") || "";
    var logEl = document.getElementById("run-console-log");
    var completeActions = root.querySelector("[data-run-complete-actions]");
    var initialStatus = root.getAttribute("data-run-status") || "";
    var progressBar = root.querySelector("[data-run-progress-bar]");
    var progressLabel = root.querySelector("[data-run-progress-label]");
    var gateRows = root.querySelectorAll("[data-run-gate-row]");
    var totalGates = gateRows.length;
    var finishedGates = 0;
    var currentGate = "";

    var isLivePlan = root.getAttribute("data-live-plan") === "1";
    var isEnvironmentVend = root.getAttribute("data-environment-vend") === "1";
    var livePlanStages = isLivePlan ? ["checkout", "plan", "policy"] : [];
    var vendStages = isEnvironmentVend ? ["validate", "render", "gates", "gitops"] : [];
    var livePlanStageLabels = {
      checkout: "Checkout target",
      plan: "Terraform plan",
      policy: "Policy evaluation",
    };
    var vendStageLabels = {
      validate: "Validate inputs",
      render: "Render stack",
      gates: "Run gates",
      gitops: "GitOps PR",
    };

    function countStagesDone(stages) {
      return stages.filter(function (stage) {
        var el = root.querySelector('[data-stage="' + stage + '"]');
        return el && el.classList.contains("is-done");
      }).length;
    }

    function activeStageFrom(stages) {
      var idx;
      for (idx = 0; idx < stages.length; idx += 1) {
        var stageEl = root.querySelector('[data-stage="' + stages[idx] + '"]');
        if (stageEl && stageEl.classList.contains("is-active")) {
          return stages[idx];
        }
      }
      return "";
    }

    function countLivePlanDone() {
      return countStagesDone(livePlanStages);
    }

    function livePlanActiveStage() {
      return activeStageFrom(livePlanStages);
    }

    function countVendDone() {
      return countStagesDone(vendStages);
    }

    function vendActiveStage() {
      return activeStageFrom(vendStages);
    }

    function updateProgressBar() {
      if (!progressBar && !progressLabel) {
        return;
      }
      var pct = 0;
      if (isLivePlan && livePlanStages.length) {
        var doneStages = countLivePlanDone();
        var activeStage = livePlanActiveStage();
        pct = activeStage
          ? Math.round(((doneStages + 0.35) / livePlanStages.length) * 100)
          : Math.round((doneStages / livePlanStages.length) * 100);
        if (progressLabel) {
          if (activeStage) {
            progressLabel.textContent =
              livePlanStageLabels[activeStage] +
              " (" +
              doneStages +
              " of " +
              livePlanStages.length +
              " complete)";
          } else if (doneStages >= livePlanStages.length) {
            progressLabel.textContent = "Live plan complete";
          } else {
            progressLabel.textContent = "Waiting for live plan…";
          }
        }
      } else if (isEnvironmentVend && vendStages.length) {
        var vendDone = countVendDone();
        var vendActive = vendActiveStage();
        pct = vendActive
          ? Math.round(((vendDone + 0.35) / vendStages.length) * 100)
          : Math.round((vendDone / vendStages.length) * 100);
        if (progressLabel) {
          if (vendActive) {
            progressLabel.textContent =
              vendStageLabels[vendActive] +
              " (" +
              vendDone +
              " of " +
              vendStages.length +
              " complete)";
          } else if (vendDone >= vendStages.length) {
            progressLabel.textContent = "Environment vend complete";
          } else {
            progressLabel.textContent = "Waiting for environment vend…";
          }
        }
      } else if (totalGates > 0) {
        pct = currentGate
          ? Math.round(((finishedGates + 0.35) / totalGates) * 100)
          : Math.round((finishedGates / totalGates) * 100);
        if (progressLabel) {
          if (currentGate) {
            progressLabel.textContent =
              "Running " + currentGate + " (" + finishedGates + " of " + totalGates + " complete)";
          } else if (finishedGates >= totalGates) {
            progressLabel.textContent = "All " + totalGates + " gates complete";
          } else {
            progressLabel.textContent = finishedGates + " of " + totalGates + " gates complete";
          }
        }
      } else if (progressLabel) {
        progressLabel.textContent = isLivePlan
          ? "Waiting for live plan…"
          : isEnvironmentVend
            ? "Waiting for environment vend…"
            : "Waiting for gates…";
      }
      pct = Math.max(0, Math.min(100, pct));
      if (progressBar) {
        progressBar.style.width = pct + "%";
      }
    }

    function appendLog(line) {
      if (!logEl) {
        return;
      }
      logEl.textContent = (logEl.textContent ? logEl.textContent + "\n" : "") + line;
      logEl.scrollTop = logEl.scrollHeight;
    }

    function setStage(stage, state) {
      var el = root.querySelector('[data-stage="' + stage + '"]');
      if (!el) {
        return;
      }
      el.classList.remove("is-active", "is-done");
      if (state === "active") {
        el.classList.add("is-active");
      } else if (state === "done") {
        el.classList.add("is-done");
      }
    }

    function setGateRow(gate, status, message) {
      var row = root.querySelector('[data-gate="' + gate + '"]');
      if (!row) {
        return;
      }
      var badge = row.querySelector("[data-gate-status]");
      if (!badge) {
        return;
      }
      badge.classList.remove("badge--muted", "badge--pass", "badge--fail", "badge--skip");
      if (status === "running") {
        badge.textContent = "Running";
        badge.classList.add("badge--muted");
        row.classList.add("is-running");
      } else if (status === "passed") {
        badge.textContent = "Passed";
        badge.classList.add("badge--pass");
        row.classList.remove("is-running");
        row.classList.add("is-done", "is-pass");
      } else if (status === "skipped") {
        badge.textContent = "Skipped";
        badge.classList.add("badge--skip");
        row.classList.remove("is-running");
        row.classList.add("is-done", "is-skip");
      } else {
        badge.textContent = "Failed";
        badge.classList.add("badge--fail");
        row.classList.remove("is-running");
        row.classList.add("is-done", "is-fail");
      }
      if (message) {
        appendLog(gate + ": " + message);
      }
    }

    function handleEvent(data) {
      if (!data || !data.kind) {
        return;
      }
      if (data.kind === "stage_started") {
        setStage(data.stage, "active");
        appendLog("Stage: " + data.stage);
      } else if (data.kind === "stage_finished") {
        setStage(data.stage, "done");
        if (isEnvironmentVend && data.stage === "gates") {
          setStage("gitops", "active");
          updateProgressBar();
        }
      } else if (data.kind === "live_plan_started") {
        setStage("checkout", "done");
        setStage("plan", "active");
        appendLog(
          "Live plan started for " +
            (data.entity_id || "entity") +
            (data.target ? " → " + data.target : "")
        );
        updateProgressBar();
      } else if (data.kind === "live_plan_finished") {
        setStage("plan", "done");
        setStage("policy", "done");
        appendLog(
          "Live plan finished: +" +
            (data.resource_add || 0) +
            " ~" +
            (data.resource_change || 0) +
            " -" +
            (data.resource_destroy || 0) +
            " (" +
            (data.gates_outcome || "unknown") +
            ")"
        );
        updateProgressBar();
      } else if (data.kind === "environment_vend_started") {
        setStage("validate", "active");
        appendLog(
          "Environment vend started" +
            (data.blueprint ? " (" + data.blueprint + ")" : "") +
            (data.gitops_path ? " → " + data.gitops_path : "")
        );
        updateProgressBar();
      } else if (data.kind === "environment_vend_finished") {
        setStage("validate", "done");
        setStage("render", "done");
        setStage("gates", "done");
        setStage("gitops", "done");
        appendLog(
          "Environment vend finished (" +
            (data.gates_outcome || "unknown") +
            ")" +
            (data.pull_request_url ? " → " + data.pull_request_url : "")
        );
        updateProgressBar();
      } else if (data.kind === "gate_started") {
        currentGate = data.gate || "";
        setGateRow(data.gate, "running", "");
        updateProgressBar();
      } else if (data.kind === "gate_finished") {
        var status = data.skipped ? "skipped" : data.passed ? "passed" : "failed";
        if (data.gate === currentGate) {
          currentGate = "";
        }
        finishedGates += 1;
        setGateRow(data.gate, status, data.message || "");
        updateProgressBar();
      } else if (data.kind === "run_finished") {
        currentGate = "";
        finishedGates = totalGates;
        updateProgressBar();
        appendLog("Run complete.");
        if (completeActions) {
          completeActions.hidden = false;
        }
        if (resultUrl && data.status === "succeeded") {
          window.setTimeout(function () {
            window.location.href = resultUrl;
          }, 800);
        }
      } else if (data.kind === "run_failed") {
        appendLog("Run failed: " + (data.error || "unknown error"));
        if (completeActions) {
          completeActions.hidden = false;
        }
      }
    }

    function pollStatus() {
      fetch("/api/v1/runs/" + encodeURIComponent(runId), { credentials: "same-origin" })
        .then(function (res) {
          return res.json();
        })
        .then(function (body) {
          if (!body || body.status !== "succeeded" || !body.result) {
            return;
          }
          if (isLivePlan || body.kind === "live_plan") {
            setStage("checkout", "done");
            setStage("plan", "done");
            setStage("policy", "done");
            updateProgressBar();
            if (completeActions) {
              completeActions.hidden = false;
            }
            return;
          }
          if (isEnvironmentVend || body.kind === "environment_vend") {
            setStage("validate", "done");
            setStage("render", "done");
            setStage("gates", "done");
            if (body.result && body.result.pull_request_url) {
              setStage("gitops", "done");
            }
            updateProgressBar();
            if (completeActions) {
              completeActions.hidden = false;
            }
            return;
          }
          if (body.result.gates) {
            finishedGates = 0;
            body.result.gates.forEach(function (gate) {
              var gateStatus = gate.skipped ? "skipped" : gate.passed ? "passed" : "failed";
              setGateRow(gate.name, gateStatus, gate.message || "");
              finishedGates += 1;
            });
            currentGate = "";
            updateProgressBar();
            if (completeActions) {
              completeActions.hidden = false;
            }
          }
        })
        .catch(function () {
          /* ignore */
        });
    }

    if (initialStatus === "succeeded" || initialStatus === "dead_letter") {
      pollStatus();
      if (completeActions) {
        completeActions.hidden = false;
      }
      return;
    }

    var source = new EventSource("/api/v1/runs/" + encodeURIComponent(runId) + "/events");
    source.onmessage = function (msg) {
      try {
        handleEvent(JSON.parse(msg.data));
      } catch (_err) {
        /* ignore */
      }
    };
    source.onerror = function () {
      source.close();
      pollStatus();
    };

    updateProgressBar();
  }

  function initResultGateAnimations() {
    var table = document.querySelector(".result-gates--animated .gate-table tbody");
    if (!table) {
      return;
    }
    var rows = table.querySelectorAll(".gate-table__row");
    rows.forEach(function (row, index) {
      row.style.animationDelay = index * 45 + "ms";
    });
  }

  function fuzzyMatchScore(query, label) {
    var q = (query || "").toLowerCase().trim();
    var text = (label || "").toLowerCase();
    if (!q) {
      return 1;
    }
    var qi = 0;
    for (var ti = 0; ti < text.length && qi < q.length; ti += 1) {
      if (text.charAt(ti) === q.charAt(qi)) {
        qi += 1;
      }
    }
    if (qi !== q.length) {
      return 0;
    }
    return q.length / Math.max(text.length, 1);
  }

  function initRelativeTimes() {
    document.querySelectorAll("time[datetime]").forEach(function (el) {
      var iso = el.getAttribute("datetime");
      if (!iso) {
        return;
      }
      var relative = formatRelativeTime(iso);
      if (!relative) {
        return;
      }
      if (!el.getAttribute("title")) {
        el.setAttribute("title", iso);
      }
      el.textContent = relative;
    });
  }

  function initSortableTables() {
    document.querySelectorAll("table[data-sortable]").forEach(function (table) {
      var tbody = table.querySelector("tbody");
      var headers = table.querySelectorAll("th[data-sortable]");
      if (!tbody || !headers.length) {
        return;
      }

      function groupedRows() {
        var groups = [];
        tbody.querySelectorAll("tr").forEach(function (row) {
          if (row.querySelector("td[colspan]")) {
            if (groups.length) {
              groups[groups.length - 1].extras.push(row);
            }
            return;
          }
          groups.push({ main: row, extras: [] });
        });
        return groups;
      }

      function cellValue(row, colIndex, sortType) {
        var cell = row.cells[colIndex];
        if (!cell) {
          return "";
        }
        var raw = cell.getAttribute("data-sort-value");
        if (raw === null) {
          raw = cell.textContent || "";
        }
        if (sortType === "number") {
          return parseFloat(raw) || 0;
        }
        if (sortType === "date") {
          return Date.parse(raw) || 0;
        }
        return String(raw).trim().toLowerCase();
      }

      headers.forEach(function (th) {
        th.setAttribute("role", "columnheader");
        th.setAttribute("aria-sort", "none");
        th.addEventListener("click", function () {
          var colIndex = th.cellIndex;
          var sortType = th.getAttribute("data-sort-type") || "text";
          var current = th.getAttribute("aria-sort");
          var ascending = current !== "ascending";
          headers.forEach(function (other) {
            other.setAttribute("aria-sort", "none");
          });
          th.setAttribute("aria-sort", ascending ? "ascending" : "descending");
          var groups = groupedRows();
          groups.sort(function (a, b) {
            var av = cellValue(a.main, colIndex, sortType);
            var bv = cellValue(b.main, colIndex, sortType);
            if (av < bv) {
              return ascending ? -1 : 1;
            }
            if (av > bv) {
              return ascending ? 1 : -1;
            }
            return 0;
          });
          groups.forEach(function (group) {
            tbody.appendChild(group.main);
            group.extras.forEach(function (extra) {
              tbody.appendChild(extra);
            });
          });
        });
      });
    });
  }

  function initCommandPalette() {
    var dataEl = document.getElementById("command-palette-data");
    var dialog = document.getElementById("command-palette");
    var input = document.getElementById("command-palette-input");
    var list = document.getElementById("command-palette-list");
    if (!dataEl || !dialog || !input || !list) {
      return;
    }
    var items = [];
    try {
      items = JSON.parse(dataEl.textContent || "[]");
    } catch (_err) {
      items = [];
    }
    var activeIndex = 0;
    var filtered = items.slice();

    function closePalette() {
      dialog.hidden = true;
      document.body.classList.remove("command-palette-open");
    }

    function openPalette() {
      dialog.hidden = false;
      document.body.classList.add("command-palette-open");
      input.value = "";
      filtered = items.slice();
      activeIndex = 0;
      renderList();
      input.focus();
    }

    function runItem(item) {
      if (!item) {
        return;
      }
      if (item.action === "resume-last-run") {
        var last = readLastRun();
        if (last && last.blueprint) {
          window.location.href = "/blueprints/" + encodeURIComponent(last.blueprint);
          return;
        }
        showToast("No last run in this browser.");
        closePalette();
        return;
      }
      if (item.href) {
        window.location.href = item.href;
      }
    }

    function renderList() {
      list.innerHTML = "";
      filtered.forEach(function (item, index) {
        var li = document.createElement("li");
        li.className = "command-palette__item" + (index === activeIndex ? " is-active" : "");
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", index === activeIndex ? "true" : "false");
        li.id = "command-palette-opt-" + index;
        var labelSpan = document.createElement("span");
        labelSpan.textContent = item.label || "";
        li.appendChild(labelSpan);
        var kind = document.createElement("span");
        kind.className = "command-palette__item-kind";
        kind.textContent = item.kind || item.action || "item";
        li.appendChild(kind);
        li.addEventListener("click", function () {
          runItem(item);
        });
        list.appendChild(li);
      });
      if (filtered[activeIndex]) {
        input.setAttribute("aria-activedescendant", "command-palette-opt-" + activeIndex);
      }
    }

    function applyFilter() {
      var query = input.value || "";
      filtered = items
        .map(function (item) {
          return { item: item, score: fuzzyMatchScore(query, item.label || "") };
        })
        .filter(function (row) {
          return row.score > 0;
        })
        .sort(function (a, b) {
          return b.score - a.score;
        })
        .map(function (row) {
          return row.item;
        });
      if (!filtered.length && !query.trim()) {
        filtered = items.slice();
      }
      activeIndex = 0;
      renderList();
    }

    document.addEventListener("keydown", function (event) {
      var mod = event.metaKey || event.ctrlKey;
      if (mod && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (dialog.hidden) {
          openPalette();
        } else {
          closePalette();
        }
        return;
      }
      if (!dialog.hidden && event.key === "/") {
        event.preventDefault();
        input.focus();
        return;
      }
      if (dialog.hidden) {
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        closePalette();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        activeIndex = Math.min(activeIndex + 1, filtered.length - 1);
        renderList();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        activeIndex = Math.max(activeIndex - 1, 0);
        renderList();
      } else if (event.key === "Enter") {
        event.preventDefault();
        runItem(filtered[activeIndex]);
      }
    });

    input.addEventListener("input", applyFilter);
    dialog.querySelectorAll("[data-command-palette-close]").forEach(function (el) {
      el.addEventListener("click", closePalette);
    });
    document.querySelectorAll("[data-command-palette-open]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openPalette();
      });
    });
    document.querySelectorAll("[data-command-palette-kbd]").forEach(function (el) {
      var isMac = navigator.platform.indexOf("Mac") === 0;
      el.textContent = isMac ? "⌘K" : "Ctrl K";
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
    initLineageReceiptCopy();
    initFileExplorer();
    initBundleMemberTabs();
    initBundlePreview();
    initBusyForms();
    initFormStepper();
    initFormDryRun();
    initHomeQuicknav();
    initCatalogSearch();
    initGateDashboard();
    initFormDraft();
    initRunConsole();
    initResultGateAnimations();
    initRelativeTimes();
    initSortableTables();
    initCommandPalette();
  });
})();
