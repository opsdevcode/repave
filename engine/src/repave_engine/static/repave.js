(function () {
  var STORAGE_KEY = "repave:lastRun";

  function safeInternalPath(url) {
    if (typeof url !== "string") {
      return "";
    }
    try {
      var parsed = new URL(url, window.location.origin);
      if (parsed.origin !== window.location.origin) {
        return "";
      }
      return parsed.pathname + parsed.search + parsed.hash;
    } catch (_err) {
      return "";
    }
  }

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

  function portalSubmitButton(form, submitter) {
    if (submitter && submitter.tagName === "BUTTON") {
      return submitter;
    }
    return (
      form.querySelector("[data-dry-run-run]:not([hidden])") ||
      form.querySelector("[data-stepper-submit]:not([hidden])") ||
      form.querySelector('button[type="submit"]:not([hidden])')
    );
  }

  function beginBusyForm(form, submitter) {
    var btn = portalSubmitButton(form, submitter);
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
    if (!btn.dataset.repaveOriginalLabel) {
      btn.dataset.repaveOriginalLabel = btn.textContent;
    }
    btn.disabled = true;
    btn.classList.add("btn--busy");
    btn.textContent = stages.length ? stages[0] : busyLabel;
    setBusyOverlay(true, stageLabel);
    if (form._repaveStageTimer) {
      clearInterval(form._repaveStageTimer);
      form._repaveStageTimer = null;
    }
    if (stages.length > 1) {
      var stageIndex = 0;
      form._repaveStageTimer = setInterval(function () {
        stageIndex = (stageIndex + 1) % stages.length;
        btn.textContent = stages[stageIndex];
        setBusyOverlay(true, stages[stageIndex]);
      }, 2200);
    }
  }

  function resetBusyForm(form) {
    setBusyOverlay(false);
    if (form._repaveStageTimer) {
      clearInterval(form._repaveStageTimer);
      form._repaveStageTimer = null;
    }
    form.querySelectorAll(".btn--busy").forEach(function (btn) {
      btn.disabled = false;
      btn.classList.remove("btn--busy");
      if (btn.dataset.repaveOriginalLabel) {
        btn.textContent = btn.dataset.repaveOriginalLabel;
      }
    });
  }

  function formatPortalErrorDetail(detail, status) {
    var text = "";
    if (Array.isArray(detail)) {
      text = detail
        .map(function (item) {
          if (item && typeof item === "object" && item.msg) {
            return String(item.msg);
          }
          return String(item);
        })
        .filter(Boolean)
        .join("; ");
    } else if (detail != null && detail !== "") {
      text = String(detail);
    }
    if (status === 401) {
      return "Sign in required. Refresh the page and sign in again.";
    }
    if (status === 403 && /insufficient role/i.test(text)) {
      return (
        "You need generator access to run this action. " +
        "Ask a platform admin to add you to the generators group (repave-generators)."
      );
    }
    if (status === 429) {
      return text || "Too many requests. Wait a moment and try again.";
    }
    if (status === 503) {
      return text || "Service temporarily unavailable. Try again shortly.";
    }
    return text || "Request failed (" + status + ").";
  }

  function showPortalSubmitError(form, message) {
    var banner = form.querySelector("[data-portal-submit-error]");
    if (!banner) {
      banner = document.createElement("p");
      banner.className = "form-validation";
      banner.setAttribute("data-portal-submit-error", "");
      banner.setAttribute("role", "alert");
      var mount = form.querySelector(".form-actions") || form;
      mount.insertBefore(banner, mount.firstChild);
    }
    banner.textContent = message;
    banner.hidden = false;
    if (typeof banner.scrollIntoView === "function") {
      banner.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function clearPortalSubmitError(form) {
    var banner = form.querySelector("[data-portal-submit-error]");
    if (!banner) {
      return;
    }
    banner.textContent = "";
    banner.hidden = true;
  }

  function shouldNativePortalSubmit(form) {
    if (form.getAttribute("data-repave-native-submit") !== null) {
      return true;
    }
    var action = (form.getAttribute("action") || form.action || "").toString();
    if (action.indexOf("/auth/logout") !== -1) {
      return true;
    }
    var streamBox = form.querySelector('input[name="stream"][value="1"]');
    if (!streamBox || streamBox.disabled) {
      return false;
    }
    // Checkbox was optional; hidden stream=1 always forces the live console path.
    if (streamBox.type === "checkbox") {
      return Boolean(streamBox.checked);
    }
    return true;
  }

  function applyPortalSuccessResponse(response, html) {
    if (response.redirected && response.url) {
      var redirected = safeInternalPath(response.url);
      if (redirected) {
        window.location.assign(redirected);
      }
      return;
    }
    var trimmed = (html || "").trim();
    if (trimmed.indexOf("<") === 0) {
      document.open();
      document.write(html);
      document.close();
      return;
    }
    if (response.url) {
      var next = safeInternalPath(response.url);
      if (next) {
        window.location.assign(next);
      }
      return;
    }
    window.location.reload();
  }

  function submitPortalForm(form, submitter) {
    clearPortalSubmitError(form);
    beginBusyForm(form, submitter);
    var action = form.getAttribute("action") || form.action || window.location.href;
    var method = (form.getAttribute("method") || "post").toUpperCase();
    var body = new FormData(form);
    if (submitter && submitter.name) {
      body.append(submitter.name, submitter.value || "");
    }
    return fetch(action, {
      method: method,
      body: body,
      credentials: "same-origin",
      headers: {
        Accept: "text/html, application/json;q=0.9, */*;q=0.8",
      },
    })
      .then(function (response) {
        var contentType = response.headers.get("content-type") || "";
        if (!response.ok) {
          if (contentType.indexOf("application/json") !== -1) {
            return response.json().then(function (payload) {
              throw {
                portalError: true,
                message: formatPortalErrorDetail(
                  payload && payload.detail,
                  response.status
                ),
              };
            });
          }
          if (contentType.indexOf("text/html") !== -1) {
            return response.text().then(function (html) {
              var doc = new DOMParser().parseFromString(html, "text/html");
              var node = doc.querySelector("[data-portal-error-message]");
              if (node) {
                throw {
                  portalError: true,
                  message:
                    node.getAttribute("data-portal-error-message") ||
                    node.textContent.trim(),
                };
              }
              throw {
                portalError: true,
                message: formatPortalErrorDetail(null, response.status),
              };
            });
          }
          return response.text().then(function (text) {
            throw {
              portalError: true,
              message: formatPortalErrorDetail(text.slice(0, 240), response.status),
            };
          });
        }
        return response.text().then(function (html) {
          applyPortalSuccessResponse(response, html);
        });
      })
      .catch(function (err) {
        resetBusyForm(form);
        var message =
          err && err.portalError
            ? err.message
            : "Network error — check your connection and try again.";
        showPortalSubmitError(form, message);
      });
  }

  function initPortalFetchSubmit() {
    document.addEventListener(
      "submit",
      function (event) {
        var form = event.target;
        if (!form || form.tagName !== "FORM") {
          return;
        }
        if (event.defaultPrevented) {
          return;
        }
        var method = (form.getAttribute("method") || "get").toLowerCase();
        if (method !== "post") {
          return;
        }
        if (shouldNativePortalSubmit(form)) {
          return;
        }
        event.preventDefault();
        submitPortalForm(form, event.submitter);
      },
      false
    );
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
          showToast("Lineage summary copied");
          button.textContent = "Copied";
          setTimeout(function () {
            button.textContent = defaultLabel;
          }, 2000);
        });
      });
    });
  }

  function copyTextToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(function () {
        return fallbackCopyText(text);
      });
    }
    return fallbackCopyText(text);
  }

  function fallbackCopyText(text) {
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try {
        if (document.execCommand("copy")) {
          resolve();
        } else {
          reject(new Error("execCommand copy failed"));
        }
      } catch (err) {
        reject(err);
      } finally {
        document.body.removeChild(ta);
      }
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

        copyTextToClipboard(text).then(onCopied).catch(function () {
          showToast("Copy failed — select the text and copy manually");
        });
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
    // Native navigation only (stream / data-repave-native-submit). Fetch submits
    // use beginBusyForm inside submitPortalForm.
    document.querySelectorAll("[data-repave-busy-form]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (event.defaultPrevented || !shouldNativePortalSubmit(form)) {
          return;
        }
        var btn = portalSubmitButton(form, event.submitter);
        if (!btn || btn.disabled) {
          return;
        }
        window.setTimeout(function () {
          if (event.defaultPrevented) {
            return;
          }
          beginBusyForm(form, event.submitter);
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
    var mode = run.dryRun ? "Plan" : "Applied";
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
    var stepperFill = form.querySelector("[data-form-stepper-fill]");
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

    function forceApplyDryRun() {
      form.querySelectorAll('input[name="dry_run"][type="radio"]').forEach(function (radio) {
        radio.checked = radio.value === "false";
      });
      setPlanSubmitMode(false);
    }

    function isApplySubmitter(submitter) {
      if (!submitter) {
        return false;
      }
      if (
        submitter === drySubmitBtn ||
        submitter.getAttribute("data-dry-run-submit") !== null ||
        submitter.getAttribute("data-dry-run-run") !== null
      ) {
        return false;
      }
      return submitter === submitBtn || submitter.type === "submit";
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
        node.classList.toggle("is-done", index < current);
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
      if (stepperFill) {
        var totalSteps = maxStep + 1;
        var fillPct = Math.round(((current + 0.35) / totalSteps) * 100);
        stepperFill.style.width = Math.min(100, fillPct) + "%";
      }
      form.dispatchEvent(
        new CustomEvent("repave:stepper-change", {
          detail: { step: current, maxStep: maxStep },
        })
      );
      form.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    if (submitBtn) {
      submitBtn.addEventListener("click", function () {
        forceApplyDryRun();
      });
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
          forcePlanDryRun();
        } else if (isApplySubmitter(submitter)) {
          forceApplyDryRun();
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

  function refreshHomeResumeChip() {
    if (
      window.repaveHome &&
      typeof window.repaveHome.refreshResumeChip === "function"
    ) {
      window.repaveHome.refreshResumeChip();
    }
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

  var IMPORT_BATCH_TARGETS_KEY = "repave:import-batch-targets";
  var IMPORT_BATCH_BLUEPRINTS_KEY = "repave:import-batch-target-blueprints";

  function mergeTargetUrls(existingText, urls) {
    var existing = existingText
      .split(/\r?\n/)
      .map(function (line) {
        return line.trim();
      })
      .filter(Boolean);
    var seen = {};
    existing.forEach(function (url) {
      seen[url] = true;
    });
    urls.forEach(function (url) {
      var trimmed = String(url).trim();
      if (trimmed && !seen[trimmed]) {
        existing.push(trimmed);
        seen[trimmed] = true;
      }
    });
    return existing.join("\n");
  }

  function initImportBatchPrefill() {
    var targets = document.getElementById("targets");
    if (!targets) {
      return;
    }
    try {
      var raw = sessionStorage.getItem(IMPORT_BATCH_TARGETS_KEY);
      var blueprintRaw = sessionStorage.getItem(IMPORT_BATCH_BLUEPRINTS_KEY);
      if (!raw) {
        return;
      }
      sessionStorage.removeItem(IMPORT_BATCH_TARGETS_KEY);
      sessionStorage.removeItem(IMPORT_BATCH_BLUEPRINTS_KEY);
      var urls = JSON.parse(raw);
      if (!Array.isArray(urls) || !urls.length) {
        return;
      }
      targets.value = mergeTargetUrls(targets.value, urls);
      var blueprintField = document.getElementById("target-blueprints-json");
      if (blueprintField && blueprintRaw) {
        var blueprints = JSON.parse(blueprintRaw);
        if (blueprints && typeof blueprints === "object") {
          blueprintField.value = JSON.stringify(blueprints);
        }
      }
      if (window.Repave && window.Repave.showToast) {
        window.Repave.showToast("Added " + urls.length + " repositories to the batch list.");
      }
    } catch (_err) {
      /* ignore invalid session payload */
    }
  }

  function initOrgScanResult() {
    var root = document.querySelector("[data-org-scan-result]");
    if (!root) {
      return;
    }
    var button = root.querySelector("[data-org-scan-add-to-batch]");
    if (!button) {
      return;
    }
    var raw = root.getAttribute("data-org-scan-urls") || "[]";
    var blueprintRaw = root.getAttribute("data-org-scan-target-blueprints") || "{}";
    button.addEventListener("click", function () {
      try {
        var urls = JSON.parse(raw);
        if (!Array.isArray(urls) || !urls.length) {
          return;
        }
        sessionStorage.setItem(IMPORT_BATCH_TARGETS_KEY, JSON.stringify(urls));
        var blueprints = JSON.parse(blueprintRaw);
        if (blueprints && typeof blueprints === "object" && Object.keys(blueprints).length) {
          sessionStorage.setItem(IMPORT_BATCH_BLUEPRINTS_KEY, JSON.stringify(blueprints));
        }
        window.location.href = "/import/batch";
      } catch (_err) {
        /* ignore */
      }
    });
  }

  function initImportOrgScan() {
    var root = document.querySelector("[data-import-org-scan]");
    if (!root) {
      return;
    }
    var orgInput = root.querySelector("[data-import-org-scan-org]");
    var runBtn = root.querySelector("[data-import-org-scan-run]");
    var skipGoverned = root.querySelector("[data-import-org-scan-skip-governed]");
    var excludeArchived = root.querySelector("[data-import-org-scan-exclude-archived]");
    var excludeForks = root.querySelector("[data-import-org-scan-exclude-forks]");
    var topicInput = root.querySelector("[data-import-org-scan-topic]");
    var languageInput = root.querySelector("[data-import-org-scan-language]");
    var pushedInput = root.querySelector("[data-import-org-scan-pushed]");
    var batchTopicInput = root.querySelector("#batch-topic");
    var resultsWrap = root.querySelector("[data-import-org-scan-results]");
    var summary = root.querySelector("[data-import-org-scan-summary]");
    var tbody = root.querySelector("[data-import-org-scan-tbody]");
    var errorNode = root.querySelector("[data-import-org-scan-error]");
    var addBtn = root.querySelector("[data-import-org-scan-add]");
    var selectAll = root.querySelector("[data-import-org-scan-select-all]");
    var targets = root.querySelector("#targets");
    if (!orgInput || !runBtn || !resultsWrap || !tbody || !targets) {
      return;
    }

    function hideError() {
      if (!errorNode) {
        return;
      }
      errorNode.hidden = true;
      errorNode.textContent = "";
    }

    function showError(message) {
      if (!errorNode) {
        return;
      }
      errorNode.hidden = false;
      errorNode.textContent = message;
    }

    function selectedFamilies() {
      return Array.prototype.slice
        .call(root.querySelectorAll("[data-import-family]:checked"))
        .map(function (node) {
          return node.value;
        });
    }

    root.querySelectorAll("[data-import-search-preset]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (languageInput) {
          languageInput.value = button.getAttribute("data-preset-language") || "";
        }
        if (topicInput) {
          topicInput.value = button.getAttribute("data-preset-topic") || "";
        }
        if (batchTopicInput && topicInput && topicInput.value) {
          batchTopicInput.value = topicInput.value;
        }
      });
    });

    function renderRows(repos) {
      tbody.textContent = "";
      repos.forEach(function (repo) {
        var row = document.createElement("tr");
        var candidate = repo && repo.top_candidate ? repo.top_candidate : null;
        var family = candidate && candidate.family ? String(candidate.family) : "—";
        var artifact = candidate && candidate.artifact_type ? String(candidate.artifact_type) : "—";
        var percent = candidate && candidate.percent ? String(candidate.percent) : "0";
        var evidence = candidate && Array.isArray(candidate.evidence) ? candidate.evidence.slice(0, 2) : [];
        var evidenceText = evidence.length ? evidence.join(", ") : "—";
        row.innerHTML =
          "<td><input type=\"checkbox\" data-import-org-scan-row checked value=\"" +
          String(repo.url).replace(/"/g, "&quot;") +
          "\" /></td>" +
          "<td><code>" +
          String(repo.name) +
          "</code></td>" +
          "<td>" +
          family +
          "</td>" +
          "<td>" +
          artifact +
          " (" +
          percent +
          "%)</td>" +
          "<td class=\"muted\">" +
          evidenceText +
          "</td>";
        tbody.appendChild(row);
      });
    }

    runBtn.addEventListener("click", function () {
      hideError();
      var org = orgInput.value.trim();
      if (!org) {
        showError("Enter a GitHub organization to scan.");
        return;
      }
      runBtn.disabled = true;
      runBtn.textContent = "Scanning…";
      var pushedSince = pushedInput && pushedInput.value ? pushedInput.value : "";
      var scanPayload = {
        org: org,
        families: selectedFamilies(),
        skip_governed: skipGoverned ? skipGoverned.checked : true,
        min_confidence: 0,
        limit: 100,
        topic: topicInput ? topicInput.value.trim() : "",
        language: languageInput ? languageInput.value.trim() : "",
        pushed_since: pushedSince,
        exclude_archived: excludeArchived ? excludeArchived.checked : true,
        exclude_forks: excludeForks ? excludeForks.checked : true,
        async: true,
      };
      fetch("/api/v2/github/org-scan", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(scanPayload),
      })
        .then(function (response) {
          if (response.status === 202) {
            return response.json().then(function (payload) {
              var runId = payload && payload.run_id ? String(payload.run_id) : "";
              if (runId) {
                window.location.href = "/runs/" + encodeURIComponent(runId);
                return null;
              }
              throw new Error("Async scan did not return a run id.");
            });
          }
          if (!response.ok) {
            return response.json().then(function (payload) {
              var detail = payload && payload.detail ? payload.detail : "Scan failed.";
              throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
            });
          }
          return response.json();
        })
        .then(function (payload) {
          if (!payload) {
            return;
          }
          var repos = Array.isArray(payload.repos) ? payload.repos : [];
          if (summary) {
            var listed = payload.listed || 0;
            var truncated = payload.truncated ? " (limit reached)" : "";
            var mode = payload.discovery_mode ? String(payload.discovery_mode) : "list";
            var query = payload.search_query ? String(payload.search_query) : "";
            summary.textContent =
              "Discovery: " +
              mode +
              (query ? " (" + query + ")" : "") +
              ". Listed " +
              listed +
              " repositories; " +
              repos.length +
              " match your filters" +
              truncated +
              ".";
          }
          renderRows(repos);
          resultsWrap.hidden = repos.length === 0;
          if (repos.length === 0) {
            showError("No repositories matched the scan filters.");
          }
        })
        .catch(function (err) {
          showError(err && err.message ? err.message : "Scan failed.");
          resultsWrap.hidden = true;
        })
        .finally(function () {
          runBtn.disabled = false;
          runBtn.textContent = "Scan org";
        });
    });

    if (selectAll) {
      selectAll.addEventListener("change", function () {
        var checked = selectAll.checked;
        tbody.querySelectorAll("[data-import-org-scan-row]").forEach(function (node) {
          node.checked = checked;
        });
      });
    }

    if (addBtn) {
      addBtn.addEventListener("click", function () {
        var existing = targets.value
          .split(/\r?\n/)
          .map(function (line) {
            return line.trim();
          })
          .filter(Boolean);
        var seen = {};
        existing.forEach(function (url) {
          seen[url] = true;
        });
        tbody.querySelectorAll("[data-import-org-scan-row]:checked").forEach(function (node) {
          var url = node.value.trim();
          if (url && !seen[url]) {
            existing.push(url);
            seen[url] = true;
          }
        });
        targets.value = existing.join("\n");
        if (window.Repave && window.Repave.showToast) {
          window.Repave.showToast("Repositories added to the batch list");
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
              if (radio.value === "true") {
                radio.checked = true;
              }
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
              if (radio.value === "false") {
                radio.checked = true;
              }
            });
          }
        },
        true
      );
    });
  }

  function initFormModeToggle() {
    var form = document.querySelector("form[data-form-mode]");
    if (!form) {
      return;
    }
    var toggle = document.getElementById("form-mode-toggle");
    if (!toggle) {
      return;
    }

    function applyMode(mode) {
      if (mode !== "guided" && mode !== "advanced") {
        return;
      }
      form.setAttribute("data-form-mode", mode);
      toggle.querySelectorAll("[data-form-mode-option]").forEach(function (input) {
        input.checked = input.value === mode;
      });
    }

    toggle.addEventListener("change", function (event) {
      var target = event.target;
      if (!target || !target.matches("[data-form-mode-option]")) {
        return;
      }
      if (target.checked) {
        applyMode(target.value);
      }
    });

    var checked = toggle.querySelector("[data-form-mode-option]:checked");
    applyMode(checked ? checked.value : "guided");
  }

  function slugifyIdentity(value, separator) {
    var sep = separator || "-";
    var text = String(value || "")
      .trim()
      .toLowerCase()
      .replace(/\/+$/, "");
    var slash = text.lastIndexOf("/");
    if (slash >= 0) {
      text = text.slice(slash + 1);
    }
    var slugs = [];
    text.replace(/,/g, " ").split(/\s+/).forEach(function (part) {
      if (!part) {
        return;
      }
      var slug = part.replace(/[^a-z0-9]+/g, sep);
      while (slug.charAt(0) === sep) {
        slug = slug.slice(1);
      }
      while (slug.charAt(slug.length - 1) === sep) {
        slug = slug.slice(0, -1);
      }
      var doubled = sep + sep;
      while (slug.indexOf(doubled) !== -1) {
        slug = slug.split(doubled).join(sep);
      }
      if (slug) {
        slugs.push(slug);
      }
    });
    return slugs.join(sep);
  }

  function humanizeIdentity(value) {
    var text = String(value || "").trim();
    if (!text) {
      return "";
    }
    var parts = text.split(",").map(function (part) {
      return part.trim();
    }).filter(Boolean);
    if (parts.length > 1) {
      return parts.join(", ");
    }
    return text.replace(/[_-]/g, " ");
  }

  function renderGuidedFrom(template, values, slug, separator) {
    var text = String(template || "").trim();
    if (!text) {
      return "";
    }
    var missing = false;
    var rendered = text.replace(/\{([a-z][a-z0-9_]*)\}/g, function (_match, key) {
      var raw = String(values[key] || "").trim();
      if (!raw) {
        missing = true;
        return "";
      }
      return slug ? slugifyIdentity(raw, separator) : humanizeIdentity(raw);
    });
    if (missing) {
      return "";
    }
    rendered = rendered.trim();
    if (!rendered) {
      return "";
    }
    if (slug) {
      return slugifyIdentity(rendered, separator);
    }
    return rendered.replace(/\s+/g, " ");
  }

  function initGuidedIdentity() {
    var form = document.querySelector("form[data-form-mode]");
    if (!form) {
      return;
    }
    var blocks = form.querySelectorAll("[data-form-identity][data-guided-from]");
    if (!blocks.length) {
      return;
    }
    var preview = form.querySelector("[data-identity-preview]");
    var previewName = form.querySelector("[data-identity-preview-name]");
    var previewDescription = form.querySelector("[data-identity-preview-description]");
    var dirty = {};

    function readValues() {
      var values = {};
      form.querySelectorAll("input[name], select[name], textarea[name]").forEach(function (field) {
        if (!field.name || field.type === "file") {
          return;
        }
        if (field.type === "checkbox") {
          values[field.name] = field.checked ? field.value || "true" : "false";
          return;
        }
        if (field.type === "radio") {
          if (field.checked) {
            values[field.name] = field.value;
          }
          return;
        }
        values[field.name] = field.value;
      });
      return values;
    }

    function identityInput(block) {
      return block.querySelector("input, textarea, select");
    }

    function syncIdentity() {
      var guided = form.getAttribute("data-form-mode") === "guided";
      var values = readValues();
      var nameText = "";
      var descriptionText = "";
      var hasNameField = false;
      blocks.forEach(function (block) {
        var input = identityInput(block);
        if (!input || !input.name) {
          return;
        }
        var template = block.getAttribute("data-guided-from") || "";
        var slug = block.getAttribute("data-guided-slug") !== "false";
        var separator = block.getAttribute("data-guided-separator") || "-";
        var rendered = renderGuidedFrom(template, values, slug, separator);
        var keepPrefill = input.hasAttribute("data-assistant-prefill");
        if (guided) {
          if (!keepPrefill) {
            dirty[input.name] = false;
          }
          input.readOnly = true;
          input.required = false;
          if (rendered && !keepPrefill) {
            input.value = rendered;
            values[input.name] = rendered;
          }
        } else {
          input.readOnly = false;
          input.required = Boolean(input.getAttribute("data-identity-required"));
          if (!dirty[input.name] && rendered && !String(input.value || "").trim()) {
            input.value = rendered;
            values[input.name] = rendered;
          }
        }
        if (input.name === "description") {
          descriptionText = String(input.value || rendered || "").trim();
        } else {
          hasNameField = true;
          nameText = String(input.value || rendered || "").trim();
        }
      });
      if (preview) {
        preview.hidden = !guided;
      }
      if (previewName) {
        previewName.hidden = !hasNameField;
        previewName.textContent = nameText || "Name appears after you make a selection";
      }
      if (previewDescription) {
        previewDescription.textContent = descriptionText;
        previewDescription.hidden = !descriptionText;
      }
    }

    blocks.forEach(function (block) {
      var input = identityInput(block);
      if (!input) {
        return;
      }
      if (input.required) {
        input.setAttribute("data-identity-required", "true");
      }
      input.addEventListener("input", function () {
        if (form.getAttribute("data-form-mode") === "advanced") {
          dirty[input.name] = true;
        }
      });
    });

    form.addEventListener("input", syncIdentity);
    form.addEventListener("change", syncIdentity);
    syncIdentity();
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
      var queryPrefill = form.querySelector("[data-assistant-prefill]");
      if (queryPrefill) {
        return;
      }
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

  var FEEDBACK_STORAGE_PREFIX = "repave:feedback:";

  function feedbackStorageKey(root) {
    var blueprint = root.getAttribute("data-blueprint") || "";
    var version = root.getAttribute("data-blueprint-version") || "";
    var runId = root.getAttribute("data-run-id") || "";
    var surface = root.getAttribute("data-surface") || "result";
    return FEEDBACK_STORAGE_PREFIX + surface + ":" + blueprint + "@" + version + ":" + runId;
  }

  function feedbackAlreadySubmitted(root) {
    try {
      return sessionStorage.getItem(feedbackStorageKey(root)) === "1";
    } catch (_err) {
      return false;
    }
  }

  function markFeedbackSubmitted(root) {
    try {
      sessionStorage.setItem(feedbackStorageKey(root), "1");
    } catch (_err2) {
      /* ignore */
    }
  }

  function readFeedbackContext(root) {
    var summaryNode = document.getElementById("result-summary-json");
    var summary = null;
    if (summaryNode) {
      try {
        summary = JSON.parse(summaryNode.textContent || "{}");
      } catch (_err3) {
        summary = null;
      }
    }
    return {
      blueprint_name:
        root.getAttribute("data-blueprint") ||
        (summary && summary.blueprint) ||
        "",
      blueprint_version:
        root.getAttribute("data-blueprint-version") ||
        (summary && summary.version) ||
        "",
      dry_run:
        root.getAttribute("data-dry-run") === "true" ||
        !!(summary && summary.dryRun),
      gates_outcome:
        root.getAttribute("data-gates-outcome") ||
        (summary && summary.outcome) ||
        "",
      run_id: root.getAttribute("data-run-id") || "",
      surface: root.getAttribute("data-surface") || "result",
    };
  }

  function collectFrictionTags(root) {
    var tags = [];
    root.querySelectorAll(".feedback-capture__tags input[type=checkbox]:checked").forEach(
      function (input) {
        if (input.value) {
          tags.push(input.value);
        }
      }
    );
    return tags;
  }

  function submitFeedbackCapture(root) {
    var selected = root.querySelector(".feedback-capture__star.is-selected");
    if (!selected) {
      showToast("Pick a rating from 1 to 5");
      return;
    }
    var ctx = readFeedbackContext(root);
    if (!ctx.blueprint_name) {
      showToast("Missing blueprint context for feedback");
      return;
    }
    var commentNode = root.querySelector(".feedback-capture__comment");
    var payload = {
      csat: Number(selected.getAttribute("data-csat")),
      friction_tags: collectFrictionTags(root),
      comment: commentNode ? commentNode.value.trim() : "",
      blueprint_name: ctx.blueprint_name,
      blueprint_version: ctx.blueprint_version,
      dry_run: ctx.dry_run,
      gates_outcome: ctx.gates_outcome,
      run_id: ctx.run_id,
      surface: ctx.surface,
    };
    fetch("/api/v2/platform/feedback", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().then(function (body) {
            throw new Error((body && body.detail) || "Feedback submit failed");
          });
        }
        markFeedbackSubmitted(root);
        root.hidden = true;
        showToast("Thanks — feedback recorded");
      })
      .catch(function (err) {
        showToast(err && err.message ? err.message : "Could not send feedback");
      });
  }

  function bindFeedbackCapture(root) {
    if (!root || feedbackAlreadySubmitted(root)) {
      if (root) {
        root.hidden = true;
      }
      return;
    }
    root.querySelectorAll(".feedback-capture__star").forEach(function (btn) {
      btn.addEventListener("click", function () {
        root.querySelectorAll(".feedback-capture__star").forEach(function (peer) {
          peer.classList.remove("is-selected");
        });
        btn.classList.add("is-selected");
      });
    });
    root.querySelectorAll(".feedback-capture__tags .chip").forEach(function (chip) {
      chip.addEventListener("click", function (event) {
        var input = chip.querySelector("input[type=checkbox]");
        if (!input) {
          return;
        }
        if (event.target === input) {
          chip.classList.toggle("is-active", input.checked);
          return;
        }
        input.checked = !input.checked;
        chip.classList.toggle("is-active", input.checked);
      });
    });
    var submitBtn = root.querySelector("[data-feedback-submit]");
    if (submitBtn) {
      submitBtn.addEventListener("click", function () {
        submitFeedbackCapture(root);
      });
    }
    var dismissBtn = root.querySelector("[data-feedback-dismiss]");
    if (dismissBtn) {
      dismissBtn.addEventListener("click", function () {
        markFeedbackSubmitted(root);
        root.hidden = true;
      });
    }
    root.hidden = false;
  }

  function initFeedbackCapture() {
    document.querySelectorAll("[data-feedback-capture]").forEach(function (root) {
      if (root.getAttribute("data-surface") === "run_console") {
        return;
      }
      bindFeedbackCapture(root);
    });
  }

  function showRunConsoleFeedback(gatesOutcome) {
    var root = document.querySelector(
      '[data-feedback-capture][data-surface="run_console"]'
    );
    if (!root || feedbackAlreadySubmitted(root)) {
      return;
    }
    if (gatesOutcome) {
      root.setAttribute("data-gates-outcome", gatesOutcome);
    }
    bindFeedbackCapture(root);
  }

  function runStatusLabel(status) {
    if (status === "dead_letter") {
      return "Dead letter";
    }
    if (status === "queued") {
      return "Queued";
    }
    if (status === "running") {
      return "Running";
    }
    if (status === "succeeded") {
      return "Succeeded";
    }
    if (status === "failed") {
      return "Failed";
    }
    return status || "Unknown";
  }

  function runStatusBadgeClass(status) {
    if (status === "succeeded") {
      return "badge badge--pass";
    }
    if (status === "failed" || status === "dead_letter") {
      return "badge badge--fail";
    }
    return "badge badge--muted";
  }

  function runTimelineDotClass(status) {
    if (status === "succeeded") {
      return "runs-timeline__dot runs-timeline__dot--pass";
    }
    if (status === "failed" || status === "dead_letter") {
      return "runs-timeline__dot runs-timeline__dot--fail";
    }
    return "runs-timeline__dot runs-timeline__dot--active";
  }

  function formatRelativeUpdated(iso) {
    if (!iso) {
      return "";
    }
    var then = Date.parse(iso);
    if (Number.isNaN(then)) {
      return iso;
    }
    var seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
    if (seconds < 45) {
      return "just now";
    }
    if (seconds < 3600) {
      return Math.round(seconds / 60) + "m ago";
    }
    if (seconds < 86400) {
      return Math.round(seconds / 3600) + "h ago";
    }
    return iso;
  }

  function runDisplayName(run) {
    if (!run) {
      return "run";
    }
    return run.blueprint || run.bundle || run.kind || "run";
  }

  function fetchRunsByStatus(status, limit) {
    var url = "/api/v1/runs?limit=" + encodeURIComponent(String(limit || 50));
    if (status) {
      url += "&status=" + encodeURIComponent(status);
    }
    return fetch(url, { credentials: "same-origin" }).then(function (res) {
      if (!res.ok) {
        throw new Error("runs list failed");
      }
      return res.json();
    });
  }

  function fetchQueuedAndRunning(limit) {
    var lim = limit || 50;
    return Promise.all([
      fetchRunsByStatus("queued", lim),
      fetchRunsByStatus("running", lim),
    ]).then(function (parts) {
      var runs = [];
      parts.forEach(function (body) {
        if (body && Array.isArray(body.runs)) {
          runs = runs.concat(body.runs);
        }
      });
      runs.sort(function (a, b) {
        return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
      });
      return {
        queued: (parts[0] && typeof parts[0].count === "number" ? parts[0].count : 0) || 0,
        running: (parts[1] && typeof parts[1].count === "number" ? parts[1].count : 0) || 0,
        runs: runs,
      };
    });
  }

  function startLivePoll(options) {
    var pollMs = options.pollMs || 3000;
    var tick = options.tick;
    var onError = options.onError;
    var inFlight = false;
    var timer = null;

    function poll() {
      if (document.hidden || inFlight) {
        return;
      }
      inFlight = true;
      Promise.resolve()
        .then(tick)
        .catch(function () {
          if (typeof onError === "function") {
            onError();
          }
        })
        .finally(function () {
          inFlight = false;
        });
    }

    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) {
        poll();
      }
    });
    poll();
    timer = window.setInterval(poll, pollMs);
    window.addEventListener(
      "beforeunload",
      function () {
        if (timer) {
          window.clearInterval(timer);
        }
      },
      { once: true }
    );
  }

  function setLiveHint(el, text) {
    if (!el) {
      return;
    }
    el.hidden = false;
    el.textContent = text;
  }

  function initPlatformOpsQueue() {
    var root = document.querySelector('[data-platform-ops-queue][data-async-queue="1"]');
    if (!root) {
      return;
    }
    var summary = root.querySelector("[data-ops-queue-summary]");
    var liveHint = root.querySelector("[data-ops-queue-live-hint]");
    var lastFingerprint = "";

    startLivePoll({
      pollMs: 3000,
      tick: function () {
        return fetchQueuedAndRunning(200).then(function (payload) {
          var queued = payload.queued || 0;
          var running = payload.running || 0;
          var inflight = queued + running;
          var next = queued + ":" + running + ":" + inflight;
          if (summary && next !== lastFingerprint) {
            summary.textContent =
              queued + " queued · " + running + " running · " + inflight + " in flight";
            lastFingerprint = next;
            setLiveHint(liveHint, "updated " + formatRelativeUpdated(new Date().toISOString()));
          } else {
            setLiveHint(liveHint, "live");
          }
        });
      },
      onError: function () {
        setLiveHint(liveHint, "refresh paused");
      },
    });
  }

  function initActivityInflight() {
    var root = document.querySelector("[data-activity-inflight]");
    if (!root) {
      return;
    }
    var emptyEl = root.querySelector("[data-activity-inflight-empty]");
    var listEl = root.querySelector("[data-activity-inflight-list]");
    var liveHint = root.querySelector("[data-activity-inflight-hint]");
    var lastFingerprint = "";

    function fingerprint(runs) {
      return runs
        .map(function (run) {
          return [
            run.run_id,
            run.status,
            run.updated_at || "",
            String(run.attempt_count || 0),
          ].join(":");
        })
        .join("|");
    }

    function renderRuns(runs) {
      if (!listEl || !emptyEl) {
        return;
      }
      while (listEl.firstChild) {
        listEl.removeChild(listEl.firstChild);
      }
      if (!runs.length) {
        emptyEl.hidden = false;
        emptyEl.textContent = "No runs in flight.";
        listEl.hidden = true;
        return;
      }
      emptyEl.hidden = true;
      listEl.hidden = false;
      runs.forEach(function (run) {
        var item = document.createElement("li");
        item.className = "activity-inflight-list__item";
        item.setAttribute("data-run-id", run.run_id || "");

        var lead = document.createElement("p");
        lead.className = "activity-inflight-list__lead";
        var name = document.createElement("code");
        name.textContent = runDisplayName(run);
        var badge = document.createElement("span");
        badge.className = runStatusBadgeClass(run.status);
        badge.textContent = runStatusLabel(run.status);
        lead.appendChild(name);
        lead.appendChild(badge);

        var meta = document.createElement("p");
        meta.className = "activity-inflight-list__meta muted";
        var user = document.createElement("span");
        user.textContent = run.acting_user || "unknown";
        var sep = document.createTextNode(" · ");
        var time = document.createElement("time");
        time.setAttribute("datetime", run.updated_at || "");
        time.textContent = formatRelativeUpdated(run.updated_at) || run.updated_at || "";
        meta.appendChild(user);
        meta.appendChild(sep);
        meta.appendChild(time);

        var actions = document.createElement("div");
        var open = document.createElement("a");
        open.className = "btn btn--ghost btn--sm";
        open.href = "/runs/" + encodeURIComponent(run.run_id || "");
        open.textContent = "Open";
        actions.appendChild(open);

        item.appendChild(lead);
        item.appendChild(meta);
        item.appendChild(actions);
        listEl.appendChild(item);
      });
    }

    startLivePoll({
      pollMs: 3000,
      tick: function () {
        return fetchQueuedAndRunning(50).then(function (payload) {
          var runs = payload.runs || [];
          var next = fingerprint(runs);
          if (next !== lastFingerprint) {
            renderRuns(runs);
            lastFingerprint = next;
            setLiveHint(liveHint, "updated " + formatRelativeUpdated(new Date().toISOString()));
          } else {
            setLiveHint(liveHint, "live");
          }
        });
      },
      onError: function () {
        if (emptyEl && listEl && !lastFingerprint) {
          emptyEl.hidden = false;
          emptyEl.textContent = "In-flight runs unavailable.";
          listEl.hidden = true;
        }
        setLiveHint(liveHint, "refresh paused");
      },
    });
  }

  function initRunsIndex() {
    var root = document.querySelector("[data-runs-index]");
    if (!root) {
      return;
    }
    var statusFilter = root.getAttribute("data-status-filter") || "";
    var canReplay = root.getAttribute("data-can-replay") === "1";
    var liveHint = root.querySelector("[data-runs-live-hint]");
    var pollMs = 3000;
    var inFlight = false;
    var timer = null;
    var lastFingerprint = "";

    function collectDomIds() {
      var ids = {};
      root.querySelectorAll("[data-run-id]").forEach(function (el) {
        var id = el.getAttribute("data-run-id");
        if (id) {
          ids[id] = true;
        }
      });
      return ids;
    }

    function ensureReplayForm(actions, runId, status) {
      if (!actions) {
        return;
      }
      var existing = actions.querySelector("[data-run-replay]");
      var terminalFail = status === "failed" || status === "dead_letter";
      if (!canReplay || !terminalFail) {
        if (existing) {
          existing.remove();
        }
        return;
      }
      if (existing) {
        return;
      }
      var form = document.createElement("form");
      form.method = "post";
      form.action = "/runs/" + encodeURIComponent(runId) + "/replay";
      form.style.display = "inline";
      form.setAttribute("data-run-replay", "");
      var button = document.createElement("button");
      button.className = "btn btn--secondary btn--sm";
      button.type = "submit";
      button.textContent = "Replay";
      form.appendChild(button);
      actions.appendChild(form);
    }

    function updateBadges(scope, run) {
      scope.querySelectorAll("[data-run-status-badge]").forEach(function (badge) {
        badge.className = runStatusBadgeClass(run.status);
        badge.setAttribute("data-status", run.status);
        badge.textContent = runStatusLabel(run.status);
      });
      scope.querySelectorAll("[data-run-updated]").forEach(function (timeEl) {
        timeEl.setAttribute("datetime", run.updated_at || "");
        timeEl.setAttribute("data-sort-value", run.updated_at || "");
        timeEl.textContent = formatRelativeUpdated(run.updated_at) || run.updated_at || "";
      });
      scope.querySelectorAll("[data-run-attempts]").forEach(function (attemptsEl) {
        attemptsEl.setAttribute("data-sort-value", String(run.attempt_count || 0));
        attemptsEl.textContent = String(run.attempt_count || 0);
      });
      scope.querySelectorAll("[data-run-attempts-label]").forEach(function (labelEl) {
        var count = run.attempt_count || 0;
        labelEl.textContent = count + (count === 1 ? " attempt" : " attempts");
      });
      scope.querySelectorAll("[data-run-timeline-dot]").forEach(function (dot) {
        dot.className = runTimelineDotClass(run.status);
      });
      scope.querySelectorAll("[data-run-actions]").forEach(function (actions) {
        ensureReplayForm(actions, run.run_id, run.status);
      });
      var errorCode = scope.querySelector("[data-run-error]");
      if (errorCode && run.error) {
        errorCode.textContent = run.error;
      }
    }

    function fingerprint(runs) {
      return runs
        .map(function (run) {
          return [
            run.run_id,
            run.status,
            run.updated_at || "",
            String(run.attempt_count || 0),
            run.error || "",
          ].join(":");
        })
        .join("|");
    }

    function syncRuns(runs) {
      if (!Array.isArray(runs)) {
        return;
      }
      var domIds = collectDomIds();
      var apiIds = {};
      var needsReload = false;
      runs.forEach(function (run) {
        if (!run || !run.run_id) {
          return;
        }
        apiIds[run.run_id] = true;
        if (!domIds[run.run_id]) {
          needsReload = true;
        }
      });
      Object.keys(domIds).forEach(function (id) {
        if (!apiIds[id]) {
          needsReload = true;
        }
      });
      if (needsReload) {
        window.location.reload();
        return;
      }
      var next = fingerprint(runs);
      if (next === lastFingerprint) {
        if (liveHint) {
          liveHint.hidden = false;
          liveHint.textContent = "live";
        }
        return;
      }
      lastFingerprint = next;
      runs.forEach(function (run) {
        var escaped =
          typeof CSS !== "undefined" && CSS.escape
            ? CSS.escape(run.run_id)
            : String(run.run_id).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
        root.querySelectorAll('[data-run-id="' + escaped + '"]').forEach(function (node) {
          updateBadges(node, run);
        });
      });
      if (liveHint) {
        liveHint.hidden = false;
        liveHint.textContent = "updated " + formatRelativeUpdated(new Date().toISOString());
      }
    }

    function poll() {
      if (document.hidden || inFlight) {
        return;
      }
      inFlight = true;
      var url = "/api/v1/runs?limit=50";
      if (statusFilter) {
        url += "&status=" + encodeURIComponent(statusFilter);
      }
      fetch(url, { credentials: "same-origin" })
        .then(function (res) {
          if (!res.ok) {
            throw new Error("runs list failed");
          }
          return res.json();
        })
        .then(function (body) {
          syncRuns((body && body.runs) || []);
        })
        .catch(function () {
          if (liveHint) {
            liveHint.hidden = false;
            liveHint.textContent = "refresh paused";
          }
        })
        .finally(function () {
          inFlight = false;
        });
    }

    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) {
        poll();
      }
    });
    poll();
    timer = window.setInterval(poll, pollMs);
    window.addEventListener(
      "beforeunload",
      function () {
        if (timer) {
          window.clearInterval(timer);
        }
      },
      { once: true }
    );
  }

  function initRunConsole() {
    var root = document.querySelector("[data-run-console]");
    if (!root) {
      return;
    }
    var runId = root.getAttribute("data-run-id");
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
    var isFleetDriftConfirm = root.getAttribute("data-fleet-drift-confirm") === "1";
    var isOrgScan = root.getAttribute("data-org-scan") === "1";
    var isEnvironmentReclaim = root.getAttribute("data-environment-reclaim") === "1";
    var isPipelineRun =
      !isLivePlan &&
      !isEnvironmentVend &&
      !isFleetDriftConfirm &&
      !isOrgScan &&
      !isEnvironmentReclaim;
    var isDryRun = root.getAttribute("data-dry-run") === "true";
    var outcomeStatus = root.querySelector("[data-run-outcome-status]");
    var publishErrorEl = root.querySelector("[data-run-publish-error]");
    var stepperFill = root.querySelector("[data-run-stepper-fill]");
    var publishChip = root.querySelector("[data-publish-chip]");
    var livePlanStages = isLivePlan ? ["checkout", "plan", "policy"] : [];
    var vendStages = isEnvironmentVend ? ["validate", "render", "gates", "gitops"] : [];
    var fleetDriftStages = isFleetDriftConfirm ? ["verify"] : [];
    var orgScanStages = isOrgScan ? ["discover", "classify"] : [];
    var reclaimStages = isEnvironmentReclaim ? ["reclaim"] : [];
    var pipelineStages = isPipelineRun ? ["validate", "render", "gates", "publish"] : [];
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
    var pipelineStageLabels = {
      validate: "Validating inputs",
      render: "Rendering templates",
      gates: "Running gates",
      publish: isDryRun ? "Previewing publish target" : "Publishing to repository",
    };
    var fleetDriftStageLabels = {
      verify: "Verifying repository pins",
    };
    var orgScanStageLabels = {
      discover: "Discovering repositories",
      classify: "Classifying repositories",
    };
    var reclaimStageLabels = {
      reclaim: "Reclaiming expired stacks",
    };
    var runComplete = false;
    var orgScanListed = 0;
    var orgScanProgressIndex = 0;
    var orgScanProgressTotal = 0;
    var progressRegion = root.querySelector("[data-run-progress]");

    gateRows.forEach(function (row, index) {
      row.classList.add("run-console__gate-row--stagger");
      row.style.animationDelay = index * 45 + "ms";
    });

    function setPublishChipState(state) {
      if (!publishChip || !state) {
        if (publishChip) {
          publishChip.classList.remove("is-live", "is-done");
        }
        return;
      }
      publishChip.classList.remove("is-live", "is-done");
      publishChip.classList.add(state);
    }

    function updateStepperFill() {
      if (!stepperFill) {
        return;
      }
      var stages = isPipelineRun
        ? pipelineStages
        : isEnvironmentVend
          ? vendStages
          : isFleetDriftConfirm
            ? fleetDriftStages
            : isOrgScan
              ? orgScanStages
              : isEnvironmentReclaim
                ? reclaimStages
                : livePlanStages;
      if (!stages.length) {
        return;
      }
      var done = countStagesDone(stages);
      var active = activeStageFrom(stages);
      var pct = done / stages.length;
      if (active) {
        pct += 0.35 / stages.length;
      }
      pct = Math.max(0, Math.min(100, Math.round(pct * 100)));
      stepperFill.style.width = pct + "%";
    }

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

    function countPipelineDone() {
      return countStagesDone(pipelineStages);
    }

    function pipelineActiveStage() {
      return activeStageFrom(pipelineStages);
    }

    function setRunBusy(busy) {
      root.classList.toggle("is-running", busy);
      if (progressRegion) {
        progressRegion.setAttribute("aria-busy", busy ? "true" : "false");
      }
    }

    function markPipelineComplete() {
      pipelineStages.forEach(function (stage) {
        setStage(stage, "done");
      });
    }

    function setPublishErrorDetail(detail) {
      if (!publishErrorEl) {
        return;
      }
      if (!detail) {
        publishErrorEl.hidden = true;
        publishErrorEl.textContent = "";
        return;
      }
      publishErrorEl.textContent = detail;
      publishErrorEl.hidden = false;
    }

    function setOutcomeStatus(message, succeeded) {
      if (!outcomeStatus || !message) {
        return;
      }
      outcomeStatus.textContent = message;
      outcomeStatus.hidden = false;
      outcomeStatus.classList.remove("run-console__outcome-status--fail");
      if (succeeded === false) {
        outcomeStatus.classList.add("run-console__outcome-status--fail");
      }
    }

    function stageLogLine(stage, started) {
      if (stage === "publish") {
        if (started) {
          return isDryRun
            ? "Publish preview — planning target repository (no GitHub write)"
            : "Publishing to repository…";
        }
        return isDryRun ? "Publish preview complete." : "Publish complete.";
      }
      var label = pipelineStageLabels[stage] || vendStageLabels[stage] || livePlanStageLabels[stage] || fleetDriftStageLabels[stage] || orgScanStageLabels[stage] || reclaimStageLabels[stage];
      if (label) {
        return started ? label + "…" : label + " complete.";
      }
      return (started ? "Stage: " : "Finished: ") + stage;
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
      } else if (isFleetDriftConfirm && fleetDriftStages.length) {
        var driftDone = countStagesDone(fleetDriftStages);
        var driftActive = activeStageFrom(fleetDriftStages);
        pct = driftActive
          ? Math.round(((driftDone + 0.35) / fleetDriftStages.length) * 100)
          : Math.round((driftDone / fleetDriftStages.length) * 100);
        if (progressLabel) {
          if (runComplete) {
            progressLabel.textContent = "Drift confirm complete — opening result…";
          } else if (driftActive) {
            progressLabel.textContent = fleetDriftStageLabels[driftActive] + "…";
          } else if (driftDone >= fleetDriftStages.length) {
            progressLabel.textContent = "Drift confirm complete";
          } else {
            progressLabel.textContent = "Waiting for drift confirm…";
          }
        }
      } else if (isOrgScan && orgScanStages.length) {
        var orgDone = countStagesDone(orgScanStages);
        var orgActive = activeStageFrom(orgScanStages);
        if (orgScanProgressTotal > 0 && orgActive === "classify") {
          pct = Math.round(
            ((orgDone + orgScanProgressIndex / orgScanProgressTotal) / orgScanStages.length) * 100
          );
        } else {
          pct = orgActive
            ? Math.round(((orgDone + 0.35) / orgScanStages.length) * 100)
            : Math.round((orgDone / orgScanStages.length) * 100);
        }
        if (progressLabel) {
          if (runComplete) {
            progressLabel.textContent = "Org scan complete — opening result…";
          } else if (orgActive === "classify" && orgScanProgressTotal > 0) {
            progressLabel.textContent =
              "Classifying " +
              orgScanProgressIndex +
              " of " +
              orgScanProgressTotal +
              " repositories…";
          } else if (orgActive) {
            progressLabel.textContent = orgScanStageLabels[orgActive] + "…";
          } else if (orgDone >= orgScanStages.length) {
            progressLabel.textContent = "Org scan complete";
          } else {
            progressLabel.textContent = "Waiting for org scan…";
          }
        }
      } else if (isEnvironmentReclaim && reclaimStages.length) {
        var reclaimDone = countStagesDone(reclaimStages);
        var reclaimActive = activeStageFrom(reclaimStages);
        pct = reclaimActive
          ? Math.round(((reclaimDone + 0.35) / reclaimStages.length) * 100)
          : Math.round((reclaimDone / reclaimStages.length) * 100);
        if (progressLabel) {
          if (runComplete) {
            progressLabel.textContent = "Reclaim complete — opening result…";
          } else if (reclaimActive) {
            progressLabel.textContent = reclaimStageLabels[reclaimActive] + "…";
          } else if (reclaimDone >= reclaimStages.length) {
            progressLabel.textContent = "Reclaim complete";
          } else {
            progressLabel.textContent = "Waiting for environment reclaim…";
          }
        }
      } else if (isPipelineRun && pipelineStages.length) {
        var pipeDone = countPipelineDone();
        var pipeActive = pipelineActiveStage();
        var stageCount = pipelineStages.length;
        if (pipeActive === "gates" && totalGates > 0) {
          var gateFrac = currentGate
            ? (finishedGates + 0.35) / totalGates
            : finishedGates / totalGates;
          pct = Math.round(((pipeDone + gateFrac) / stageCount) * 100);
        } else if (pipeActive) {
          pct = Math.round(((pipeDone + 0.35) / stageCount) * 100);
        } else {
          pct = Math.round((pipeDone / stageCount) * 100);
        }
        if (progressLabel) {
          if (runComplete) {
            progressLabel.textContent = isDryRun
              ? "Plan complete — loading file preview…"
              : "Apply complete — opening result…";
          } else if (pipeActive === "gates" && currentGate) {
            progressLabel.textContent =
              "Running " +
              currentGate +
              " (" +
              finishedGates +
              " of " +
              totalGates +
              " gates)";
          } else if (pipeActive === "gates" && finishedGates >= totalGates && totalGates > 0) {
            progressLabel.textContent = "All gates passed — preparing publish…";
          } else if (pipeActive) {
            progressLabel.textContent = (pipelineStageLabels[pipeActive] || pipeActive) + "…";
          } else if (pipeDone >= stageCount) {
            progressLabel.textContent = isDryRun
              ? "Plan complete — finalizing preview…"
              : "Saving run results…";
          } else if (pipeDone > 0) {
            progressLabel.textContent =
              pipeDone + " of " + stageCount + " stages complete";
          } else {
            progressLabel.textContent = "Starting apply…";
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
            : isFleetDriftConfirm
              ? "Waiting for drift confirm…"
              : isOrgScan
                ? "Waiting for org scan…"
                : isEnvironmentReclaim
                ? "Waiting for environment reclaim…"
                : "Starting apply…";
      }
      pct = Math.max(0, Math.min(100, pct));
      if (progressBar) {
        progressBar.style.width = pct + "%";
      }
      updateStepperFill();
    }

    function appendLog(line) {
      if (!logEl) {
        return;
      }
      logEl.hidden = false;
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
        appendLog(stageLogLine(data.stage, true));
        updateProgressBar();
      } else if (data.kind === "stage_finished") {
        setStage(data.stage, "done");
        appendLog(stageLogLine(data.stage, false));
        if (isEnvironmentVend && data.stage === "gates") {
          setStage("gitops", "active");
        }
        // Publish events can arrive before status flips to succeeded — poll until
        // terminal, but do not unhide Browse/result until the store says succeeded.
        if (isPipelineRun && data.stage === "publish") {
          updateProgressBar();
          if (progressLabel && isDryRun) {
            progressLabel.textContent = "Plan complete — finalizing preview…";
          }
          pollUntilTerminal(30, 500);
          return;
        }
        updateProgressBar();
      } else if (data.kind === "publish_progress") {
        if (data.message) {
          appendLog(data.message);
        }
        setPublishChipState("is-live");
        setOutcomeStatus(data.message || "", true);
        updateProgressBar();
      } else if (data.kind === "publish_finished") {
        if (data.summary) {
          appendLog(data.summary);
          setOutcomeStatus(data.summary, data.succeeded !== false);
        }
        if (data.succeeded === false && data.detail) {
          appendLog(data.detail);
          setPublishErrorDetail(data.detail);
        } else {
          setPublishErrorDetail("");
        }
        setPublishChipState(data.succeeded !== false ? "is-done" : "");
        updateProgressBar();
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
      } else if (data.kind === "fleet_drift_confirm_started") {
        setStage("verify", "active");
        appendLog(
          "Fleet drift confirm started for " + (data.repo_count || 0) + " repositories"
        );
        updateProgressBar();
      } else if (data.kind === "fleet_drift_confirm_finished") {
        setStage("verify", "done");
        appendLog(
          "Fleet drift confirm finished: " +
            (data.confirmed_current || 0) +
            " current, " +
            (data.confirmed_behind || 0) +
            " behind"
        );
        updateProgressBar();
      } else if (data.kind === "org_scan_started") {
        setStage("discover", "active");
        orgScanListed = data.listed || 0;
        appendLog(
          "Org scan started for " +
            (data.org || "organization") +
            (data.discovery_mode ? " (" + data.discovery_mode + ")" : "") +
            (orgScanListed ? " — listed " + orgScanListed : "")
        );
        updateProgressBar();
      } else if (data.kind === "org_scan_progress") {
        setStage("discover", "done");
        setStage("classify", "active");
        orgScanProgressIndex = data.index || 0;
        orgScanProgressTotal = data.total || 0;
        if (data.repo) {
          appendLog(
            "Classified " +
              (data.repo || "repository") +
              (data.matched ? " (match)" : "")
          );
        }
        updateProgressBar();
      } else if (data.kind === "org_scan_finished") {
        setStage("discover", "done");
        setStage("classify", "done");
        appendLog(
          "Org scan finished: " +
            (data.matched || 0) +
            " matched of " +
            (data.listed || orgScanListed || 0) +
            " listed" +
            (data.truncated ? " (limit reached)" : "")
        );
        updateProgressBar();
      } else if (data.kind === "environment_reclaim_started") {
        setStage("reclaim", "active");
        appendLog(
          "Environment reclaim started" + (data.dry_run ? " (dry run)" : "")
        );
        updateProgressBar();
      } else if (data.kind === "environment_reclaim_finished") {
        setStage("reclaim", "done");
        appendLog(
          "Environment reclaim finished: " +
            (data.reclaimed_count || 0) +
            " reclaimed, " +
            (data.skipped_count || 0) +
            " skipped"
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
        runComplete = true;
        if (data.status) {
          root.setAttribute("data-run-status", data.status);
        }
        // Dry-run still needs status polls to load rendered_files into the preview.
        if (!(isDryRun && isPipelineRun)) {
          stopStatusPolling();
        }
        if (isPipelineRun) {
          markPipelineComplete();
        } else if (isFleetDriftConfirm) {
          setStage("verify", "done");
        } else if (isOrgScan) {
          setStage("discover", "done");
          setStage("classify", "done");
        } else if (isEnvironmentReclaim) {
          setStage("reclaim", "done");
        }
        setRunBusy(false);
        root.classList.add("is-complete");
        updateProgressBar();
        if (progressLabel) {
          if (isFleetDriftConfirm) {
            progressLabel.textContent = "Drift confirm complete — opening result…";
          } else if (isOrgScan) {
            progressLabel.textContent = "Org scan complete — opening result…";
          } else if (isEnvironmentReclaim) {
            progressLabel.textContent = "Reclaim complete — opening result…";
          } else {
            progressLabel.textContent = isDryRun
              ? "Plan complete — loading file preview…"
              : "Apply complete — opening result…";
          }
        }
        appendLog("Run complete.");
        if (completeActions && data.status === "succeeded") {
          completeActions.hidden = false;
        }
        showRunConsoleFeedback(data.gates_outcome || "");
        if (resultCta && data.status === "succeeded") {
          if (data.publish_succeeded === false) {
            if (progressLabel) {
              progressLabel.textContent = "Gates passed — publish failed (see error below)";
            }
            appendLog("Publish failed — review the error above or open the result page.");
          } else if (isDryRun) {
            if (progressLabel) {
              progressLabel.textContent = "Plan complete — loading file preview…";
            }
            // Must keep polling after runComplete — see pollUntilTerminal.
            pollUntilTerminal(25, 400);
          } else {
            scheduleResultRedirect();
          }
        }
      } else if (data.kind === "run_failed") {
        runComplete = true;
        stopStatusPolling();
        setRunBusy(false);
        root.classList.add("is-failed");
        if (progressLabel) {
          progressLabel.textContent = "Apply failed";
        }
        updateProgressBar();
        appendLog("Run failed: " + (data.error || "unknown error"));
        if (completeActions) {
          completeActions.hidden = false;
        }
      }
    }

    var pollTimer = null;
    var redirectScheduled = false;
    var previewSettled = false;
    var browsePending = false;
    var dryRunPollWaves = 0;
    var resultCta = root.querySelector("[data-run-result-cta]");

    function stopStatusPolling() {
      if (pollTimer) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
    }

    function scheduleResultRedirect(delayMs) {
      if (redirectScheduled || !resultCta) {
        return;
      }
      redirectScheduled = true;
      previewSettled = true;
      window.setTimeout(function () {
        // Server-rendered <a href> — do not assign DOM text to location.
        resultCta.click();
      }, typeof delayMs === "number" ? delayMs : 800);
    }

    function runStatusIsSucceeded() {
      return (root.getAttribute("data-run-status") || "") === "succeeded";
    }

    function revealDryRunBrowseFallback() {
      if (!isDryRun) {
        return;
      }
      // Never unhide Browse while status is still running — /result 303s back here.
      if (!runStatusIsSucceeded()) {
        dryRunPollWaves += 1;
        if (dryRunPollWaves < 4) {
          if (progressLabel) {
            progressLabel.textContent = "Plan complete — still saving preview…";
          }
          pollUntilTerminal(30, 750);
          return;
        }
        previewSettled = true;
        setRunBusy(false);
        if (progressLabel) {
          progressLabel.textContent =
            "Preview save is taking longer than expected — refresh this page";
        }
        appendLog(
          "Run status has not reached succeeded yet — refresh, then use Browse generated files."
        );
        return;
      }
      previewSettled = true;
      setRunBusy(false);
      if (completeActions) {
        completeActions.hidden = false;
      }
      if (progressLabel) {
        progressLabel.textContent = "Plan complete — open Browse for generated files";
      }
      if (browsePending) {
        scheduleResultRedirect(0);
      }
    }

    function pollUntilTerminal(maxAttempts, delayMs) {
      var attempts = 0;
      function tick() {
        // Do not bail on runComplete for dry-run: run_finished sets that flag before
        // rendered_files are available on GET /api/v1/runs/{id}.
        if (redirectScheduled || previewSettled) {
          return;
        }
        if (runComplete && !isDryRun) {
          return;
        }
        pollStatus();
        attempts += 1;
        if (redirectScheduled || previewSettled) {
          return;
        }
        if (runComplete && !isDryRun) {
          return;
        }
        if (attempts < maxAttempts) {
          window.setTimeout(tick, delayMs || 500);
          return;
        }
        revealDryRunBrowseFallback();
      }
      tick();
    }

    if (resultCta) {
      resultCta.addEventListener("click", function (event) {
        if (runStatusIsSucceeded()) {
          return;
        }
        // Avoid the /result → console 303 loop while the worker finalizes the run.
        event.preventDefault();
        browsePending = true;
        previewSettled = false;
        dryRunPollWaves = 0;
        if (progressLabel) {
          progressLabel.textContent = "Still saving preview — opening Browse when ready…";
        }
        showToast("Preview is still saving — opening when ready…");
        pollUntilTerminal(40, 500);
      });
    }

    var filePreviewRoot = root.querySelector("[data-run-file-preview]");
    var filePreviewList = root.querySelector("[data-run-file-preview-list]");
    var filePreviewPane = root.querySelector("[data-run-file-preview-pane]");
    var filePreviewContent = root.querySelector("[data-run-file-preview-content]");
    var filePreviewCopy = root.querySelector("[data-run-file-preview-copy]");
    var previewFiles = [];
    var previewIndex = 0;

    function bindPreviewTab(button, index) {
      button.addEventListener("click", function () {
        previewIndex = index;
        Array.prototype.forEach.call(
          filePreviewList.querySelectorAll(".run-console__preview-tab"),
          function (tab, tabIndex) {
            tab.classList.toggle("is-active", tabIndex === index);
          }
        );
        if (filePreviewContent) {
          filePreviewContent.textContent = previewFiles[index].content || "";
        }
      });
    }

    function renderRunFilePreview(files) {
      if (!filePreviewRoot || !filePreviewList || !Array.isArray(files) || !files.length) {
        return false;
      }
      var usable = files.filter(function (file) {
        return file && typeof file.path === "string" && typeof file.content === "string";
      });
      if (!usable.length) {
        return false;
      }
      previewFiles = usable;
      previewIndex = 0;
      while (filePreviewList.firstChild) {
        filePreviewList.removeChild(filePreviewList.firstChild);
      }
      usable.forEach(function (file, index) {
        var item = document.createElement("li");
        var button = document.createElement("button");
        button.type = "button";
        button.className =
          "run-console__preview-tab" + (index === 0 ? " is-active" : "");
        button.textContent = file.path;
        button.setAttribute("data-preview-index", String(index));
        bindPreviewTab(button, index);
        item.appendChild(button);
        filePreviewList.appendChild(item);
      });
      if (filePreviewContent) {
        filePreviewContent.textContent = usable[0].content || "";
      }
      if (filePreviewPane) {
        filePreviewPane.hidden = false;
      }
      filePreviewRoot.hidden = false;
      return true;
    }

    var previewJsonEl = root.querySelector("[data-run-file-preview-json]");
    if (previewJsonEl) {
      try {
        renderRunFilePreview(JSON.parse(previewJsonEl.textContent || "[]"));
      } catch (_err) {
        /* keep SSR markup; clicks may be unbound */
        Array.prototype.forEach.call(
          filePreviewList ? filePreviewList.querySelectorAll(".run-console__preview-tab") : [],
          function (tab) {
            var index = Number(tab.getAttribute("data-preview-index") || "0");
            bindPreviewTab(tab, index);
          }
        );
      }
    }

    if (filePreviewCopy && filePreviewContent) {
      filePreviewCopy.addEventListener("click", function () {
        var text = filePreviewContent.textContent || "";
        if (!text) {
          return;
        }
        copyTextToClipboard(text)
          .then(function () {
            showToast("Copied " + (previewFiles[previewIndex] && previewFiles[previewIndex].path
              ? previewFiles[previewIndex].path
              : "file"));
          })
          .catch(function () {
            showToast("Copy failed — select the text and copy manually");
          });
      });
    }

    function applyTerminalFromPoll(body) {
      var status = body.status || "";
      root.setAttribute("data-run-status", status);
      setRunBusy(false);
      if (completeActions) {
        completeActions.hidden = false;
      }
      if (status === "failed" || status === "dead_letter") {
        runComplete = true;
        root.classList.add("is-failed");
        if (progressLabel) {
          progressLabel.textContent = "Run failed";
        }
        appendLog("Run failed: " + (body.error || "unknown error"));
        if (body.result && body.result.gates) {
          body.result.gates.forEach(function (gate) {
            var gateStatus = gate.skipped ? "skipped" : gate.passed ? "passed" : "failed";
            setGateRow(gate.name, gateStatus, gate.message || "");
          });
        }
        updateProgressBar();
        stopStatusPolling();
        return;
      }
      if (status !== "succeeded") {
        return;
      }
      runComplete = true;
      root.classList.add("is-complete");
      if (isLivePlan || body.kind === "live_plan") {
        setStage("checkout", "done");
        setStage("plan", "done");
        setStage("policy", "done");
        updateProgressBar();
        stopStatusPolling();
        scheduleResultRedirect();
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
        stopStatusPolling();
        scheduleResultRedirect();
        return;
      }
      if (isFleetDriftConfirm || body.kind === "fleet_drift_confirm") {
        setStage("verify", "done");
        updateProgressBar();
        stopStatusPolling();
        scheduleResultRedirect();
        return;
      }
      if (isOrgScan || body.kind === "org_scan") {
        setStage("discover", "done");
        setStage("classify", "done");
        updateProgressBar();
        stopStatusPolling();
        scheduleResultRedirect();
        return;
      }
      if (isEnvironmentReclaim || body.kind === "environment_reclaim") {
        setStage("reclaim", "done");
        updateProgressBar();
        stopStatusPolling();
        scheduleResultRedirect();
        return;
      }
      if (body.result && body.result.gates) {
        finishedGates = 0;
        body.result.gates.forEach(function (gate) {
          var gateStatus = gate.skipped ? "skipped" : gate.passed ? "passed" : "failed";
          setGateRow(gate.name, gateStatus, gate.message || "");
          finishedGates += 1;
        });
        currentGate = "";
        if (isPipelineRun) {
          markPipelineComplete();
        }
        updateProgressBar();
      }
      stopStatusPolling();
      var showedPreview =
        isDryRun &&
        body.result &&
        renderRunFilePreview(body.result.rendered_files);
      if (showedPreview) {
        previewSettled = true;
        if (completeActions) {
          completeActions.hidden = false;
        }
        if (progressLabel) {
          progressLabel.textContent = "Plan preview ready — browse files below";
        }
        if (browsePending) {
          scheduleResultRedirect(0);
          return;
        }
        // Keep dry-run previews on the console; full result is one click away.
        return;
      }
      if (isDryRun) {
        // Snapshot may be a count or empty while artifacts rehydrate on /result.
        if (completeActions) {
          completeActions.hidden = false;
        }
        if (progressLabel) {
          progressLabel.textContent = "Plan complete — opening full result…";
        }
        previewSettled = true;
        scheduleResultRedirect(browsePending ? 0 : 800);
        return;
      }
      scheduleResultRedirect();
    }

    function pollStatus() {
      fetch("/api/v1/runs/" + encodeURIComponent(runId), { credentials: "same-origin" })
        .then(function (res) {
          return res.json();
        })
        .then(function (body) {
          if (!body || !body.status) {
            return;
          }
          root.setAttribute("data-run-status", body.status);
          if (body.status === "queued" || body.status === "running") {
            if (progressLabel && !runComplete) {
              progressLabel.textContent =
                body.status === "queued" ? "Queued…" : progressLabel.textContent || "Running…";
            }
            return;
          }
          applyTerminalFromPoll(body);
        })
        .catch(function () {
          /* ignore transient poll errors */
        });
    }

    function startStatusPolling() {
      if (pollTimer || previewSettled || redirectScheduled) {
        return;
      }
      if (runComplete && !isDryRun) {
        return;
      }
      pollTimer = window.setInterval(function () {
        if (previewSettled || redirectScheduled) {
          stopStatusPolling();
          return;
        }
        if (runComplete && !isDryRun) {
          stopStatusPolling();
          return;
        }
        pollStatus();
      }, 4000);
    }

    if (
      initialStatus === "succeeded" ||
      initialStatus === "failed" ||
      initialStatus === "dead_letter"
    ) {
      runComplete = initialStatus === "succeeded";
      setRunBusy(false);
      root.classList.add(initialStatus === "succeeded" ? "is-complete" : "is-failed");
      pollStatus();
      if (completeActions) {
        completeActions.hidden = false;
      }
      return;
    }

    setRunBusy(true);
    var source = new EventSource("/api/v1/runs/" + encodeURIComponent(runId) + "/events");
    source.onmessage = function (msg) {
      try {
        handleEvent(JSON.parse(msg.data));
      } catch (_err) {
        /* ignore */
      }
    };
    source.onerror = function () {
      // Keep EventSource open so the browser can reconnect; poll fills gaps.
      pollStatus();
      startStatusPolling();
    };

    // Immediate status check — do not wait for the first 4s interval tick.
    pollStatus();
    startStatusPolling();
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
        var icon = document.createElement("span");
        icon.className =
          "command-palette__item-icon command-palette__item-icon--" + (item.kind || "item");
        icon.setAttribute("aria-hidden", "true");
        li.appendChild(icon);
        var body = document.createElement("div");
        body.className = "command-palette__item-body";
        var labelSpan = document.createElement("span");
        labelSpan.className = "command-palette__item-label";
        labelSpan.textContent = item.label || "";
        body.appendChild(labelSpan);
        if (item.subtitle) {
          var subtitle = document.createElement("span");
          subtitle.className = "command-palette__item-subtitle";
          subtitle.textContent = item.subtitle;
          body.appendChild(subtitle);
        } else {
          var kind = document.createElement("span");
          kind.className = "command-palette__item-kind";
          kind.textContent = item.kind || item.action || "item";
          body.appendChild(kind);
        }
        li.appendChild(body);
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
          var labelScore = fuzzyMatchScore(query, item.label || "");
          var subtitleScore = fuzzyMatchScore(query, item.subtitle || "");
          return { item: item, score: Math.max(labelScore, subtitleScore) };
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

  function initEstateMap() {
    var root = document.querySelector("[data-estate-map]");
    if (!root) {
      return;
    }
    var input = root.querySelector("[data-estate-search-input]");
    var meta = root.querySelector("[data-estate-filter-meta]");
    var emptyState = document.querySelector("[data-estate-empty]");
    var tiles = document.querySelectorAll("[data-estate-tile]");
    var rows = document.querySelectorAll("[data-estate-row]");
    var chips = root.querySelectorAll("[data-estate-filter]");
    var activeFilter = "all";

    function normalize(value) {
      return (value || "").toLowerCase().trim();
    }

    function matchesSearch(node) {
      if (!input) {
        return true;
      }
      var query = normalize(input.value);
      var terms = query ? query.split(/\s+/).filter(Boolean) : [];
      if (!terms.length) {
        return true;
      }
      var haystack = normalize(node.getAttribute("data-search-text"));
      return terms.every(function (term) {
        return haystack.indexOf(term) !== -1;
      });
    }

    function matchesFilter(node) {
      if (activeFilter === "all") {
        return true;
      }
      return node.getAttribute("data-estate-freshness") === activeFilter;
    }

    function applyFilters() {
      var visible = 0;
      tiles.forEach(function (tile) {
        var show = matchesSearch(tile) && matchesFilter(tile);
        tile.hidden = !show;
        if (show) {
          visible += 1;
        }
      });
      rows.forEach(function (row) {
        row.hidden = !(matchesSearch(row) && matchesFilter(row));
      });
      if (meta) {
        if (visible === 0) {
          meta.hidden = false;
          meta.textContent = "No repositories match the current search or filter.";
        } else {
          meta.hidden = true;
          meta.textContent = "";
        }
      }
      if (emptyState) {
        emptyState.hidden = visible > 0;
      }
    }

    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        activeFilter = chip.getAttribute("data-estate-filter") || "all";
        chips.forEach(function (item) {
          var active = item === chip;
          item.classList.toggle("is-active", active);
          item.setAttribute("aria-pressed", active ? "true" : "false");
        });
        applyFilters();
      });
    });

    if (input) {
      input.addEventListener("input", applyFilters);
    }
    applyFilters();
  }

  function initPortalViewToggle() {
    document.querySelectorAll("[data-portal-view-toggle]").forEach(function (root) {
      var buttons = root.querySelectorAll("[data-view-mode]");
      var panels = root.querySelectorAll("[data-view-panel]");
      if (!buttons.length || panels.length < 2) {
        return;
      }
      function setMode(mode) {
        buttons.forEach(function (button) {
          var active = button.getAttribute("data-view-mode") === mode;
          button.classList.toggle("is-active", active);
          button.setAttribute("aria-pressed", active ? "true" : "false");
        });
        panels.forEach(function (panel) {
          var show = panel.getAttribute("data-view-panel") === mode;
          panel.hidden = !show;
        });
      }
      buttons.forEach(function (button) {
        button.addEventListener("click", function () {
          setMode(button.getAttribute("data-view-mode") || "list");
        });
      });
      var initial = root.querySelector("[data-view-mode].is-active");
      setMode(initial ? initial.getAttribute("data-view-mode") || "list" : "list");
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
      refreshHomeResumeChip();
    },
    renderLastRun: function () {
      renderLastRun();
      refreshHomeResumeChip();
    },
    showToast: showToast,
    showSubmitError: showPortalSubmitError,
    formatErrorDetail: formatPortalErrorDetail,
  };

  function initChoiceTiles() {
    document.querySelectorAll(".fleet-tile--choice").forEach(function (tile) {
      tile.addEventListener("click", function () {
        var input = tile.querySelector('input[type="radio"]');
        if (!input || input.disabled) {
          return;
        }
        input.checked = true;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderLastRun();
    refreshHomeResumeChip();
    initCopyButtons();
    initLineageReceiptCopy();
    initFileExplorer();
    initBundleMemberTabs();
    initBundlePreview();
    initBusyForms();
    initFormStepper();
    initFormModeToggle();
    initGuidedIdentity();
    initFormDryRun();
    initPortalFetchSubmit();
    initGateDashboard();
    initImportOrgScan();
    initImportBatchPrefill();
    initOrgScanResult();
    initFeedbackCapture();
    initFormDraft();
    initRunsIndex();
    initPlatformOpsQueue();
    initActivityInflight();
    initRunConsole();
    initResultGateAnimations();
    initRelativeTimes();
    initSortableTables();
    initCommandPalette();
    initPortalViewToggle();
    initEstateMap();
    initChoiceTiles();
  });
})();
