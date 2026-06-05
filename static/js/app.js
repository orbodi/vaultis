/** vaultis app.js v20260607 */
/**
 * Sauvegarde : validation, modal de confirmation, overlay de progression.
 */
document.addEventListener("DOMContentLoaded", function () {
  var progressOverlay = document.getElementById("backupProgressOverlay");
  var progressFill = progressOverlay
    ? progressOverlay.querySelector(".js-backup-progress-fill")
    : null;
  var progressStatus = progressOverlay
    ? progressOverlay.querySelector(".js-backup-progress-status")
    : null;
  var progressEquipment = progressOverlay
    ? progressOverlay.querySelector(".js-backup-progress-equipment")
    : null;
  var progressBar = progressOverlay
    ? progressOverlay.querySelector(".backup-progress-bar")
    : null;

  var progressTimer = null;
  var statusTimer = null;
  var progressValue = 0;
  var unloadHooked = false;

  var defaultStatusMessages = [
    "Connexion à l’équipement…",
    "Exécution de la sauvegarde…",
    "Finalisation…",
  ];

  var arborStatusMessages = [
    "Lecture des fichiers source Arbor AED…",
    "Classement full / inc et copie locale…",
    "Transfert SCP vers la VM Windows…",
    "Envoi des volumes (opération longue)…",
  ];

  if (progressOverlay && progressOverlay.parentElement !== document.body) {
    document.body.appendChild(progressOverlay);
  }

  function clearProgressTimers() {
    if (progressTimer) {
      window.clearInterval(progressTimer);
      progressTimer = null;
    }
    if (statusTimer) {
      window.clearInterval(statusTimer);
      statusTimer = null;
    }
  }

  function setProgressValue(value) {
    progressValue = Math.min(92, Math.max(0, value));
    if (progressFill) {
      progressFill.style.width = progressValue + "%";
    }
    if (progressBar) {
      progressBar.setAttribute("aria-valuenow", String(Math.round(progressValue)));
    }
  }

  function startStatusRotation(messages) {
    if (!progressStatus || !messages.length) {
      return;
    }
    var index = 0;
    progressStatus.textContent = messages[0];
    statusTimer = window.setInterval(function () {
      index = (index + 1) % messages.length;
      progressStatus.textContent = messages[index];
    }, 6000);
  }

  function preventUnloadWhileBackup(event) {
    event.preventDefault();
    event.returnValue = "";
  }

  function showBackupProgress(options) {
    if (!progressOverlay) {
      return false;
    }

    clearProgressTimers();
    progressValue = 8;
    setProgressValue(8);

    if (progressEquipment && options.equipmentName) {
      progressEquipment.textContent = options.equipmentName;
    }

    var messages = options.isArbor ? arborStatusMessages : defaultStatusMessages;
    startStatusRotation(messages);

    progressOverlay.classList.remove("d-none");
    progressOverlay.classList.add("backup-progress-overlay--visible");
    progressOverlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("backup-in-progress");

    progressTimer = window.setInterval(function () {
      var remaining = 92 - progressValue;
      var step = remaining > 30 ? 1.2 : remaining > 10 ? 0.35 : 0.08;
      setProgressValue(progressValue + step);
    }, 900);

    if (!unloadHooked) {
      window.addEventListener("beforeunload", preventUnloadWhileBackup);
      unloadHooked = true;
    }

    return true;
  }

  function bindBackupProgressOnSubmit(form) {
    if (!form || !progressOverlay) {
      return;
    }

    var equipmentTitle = document.querySelector(".app-page-title");
    var isArborForm = Boolean(form.getAttribute("data-arbor-dcs"));
    var allowNativeSubmit = false;

    form.addEventListener("submit", function (event) {
      if (allowNativeSubmit) {
        return;
      }
      event.preventDefault();
      showBackupProgress({
        equipmentName: equipmentTitle ? equipmentTitle.textContent.trim() : "",
        isArbor: isArborForm,
      });
      allowNativeSubmit = true;
      window.setTimeout(function () {
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          HTMLFormElement.prototype.submit.call(form);
        }
      }, 200);
    });
  }

  document.querySelectorAll(".js-schedule-form").forEach(function (form) {
    var frequencySelect = form.querySelector(".js-schedule-frequency");
    var weeklyField = form.querySelector(".js-schedule-field-weekly");
    var monthlyField = form.querySelector(".js-schedule-field-monthly");

    function syncScheduleFields() {
      var value = frequencySelect ? frequencySelect.value : "daily";
      if (weeklyField) {
        weeklyField.classList.toggle("d-none", value !== "weekly");
      }
      if (monthlyField) {
        monthlyField.classList.toggle("d-none", value !== "monthly");
      }
    }

    if (frequencySelect) {
      frequencySelect.addEventListener("change", syncScheduleFields);
    }
    syncScheduleFields();
  });

  var modalEl = document.getElementById("backupConfirmModal");

  document.querySelectorAll(".js-backup-form").forEach(function (form) {
    bindBackupProgressOnSubmit(form);

    var openBtn = form.querySelector(".js-backup-open");
    if (!openBtn) {
      return;
    }

    if (!modalEl) {
      openBtn.addEventListener("click", function (event) {
        event.preventDefault();
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          form.submit();
        }
      });
      return;
    }

    if (modalEl.parentElement !== document.body) {
      document.body.appendChild(modalEl);
    }

    var modal =
      typeof bootstrap !== "undefined"
        ? bootstrap.Modal.getOrCreateInstance(modalEl)
        : null;

    var hostSelect = form.querySelector('select[name="equipment_host_id"]');
    var usernameInput = form.querySelector('[name="api_username"]');
    var passwordInput = form.querySelector('[name="api_password"]');
    var formErrors = form.querySelector(".js-backup-form-errors");
    var summaryEl = modalEl.querySelector(".js-backup-modal-summary");
    var confirmBtn = modalEl.querySelector(".js-backup-confirm");
    var credentialsModeInput = form.querySelector('input[name="credentials_mode"]');
    var customCredentialsEl = form.querySelector(".js-custom-credentials");
    var defaultSummaryEl = form.querySelector(".js-credentials-default-summary");
    var showCustomBtn = form.querySelector(".js-toggle-custom-credentials");
    var forceCustomCredentials =
      customCredentialsEl && customCredentialsEl.getAttribute("data-force-visible") === "true";

    var rules = [];
    if (hostSelect) {
      rules.push({
        field: hostSelect,
        errorEl: document.getElementById("host-error"),
        label: "host cible",
        isValid: function () {
          return Boolean(hostSelect.value);
        },
      });
    }
    if (usernameInput) {
      rules.push({
        field: usernameInput,
        errorEl: document.getElementById("username-error"),
        label: "identifiant",
        isValid: function () {
          return Boolean(usernameInput.value.trim());
        },
      });
    }
    if (passwordInput) {
      rules.push({
        field: passwordInput,
        errorEl: document.getElementById("password-error"),
        label: "mot de passe",
        isValid: function () {
          return Boolean(passwordInput.value);
        },
      });
    }

    function isCustomCredentials() {
      if (forceCustomCredentials) {
        return true;
      }
      if (!credentialsModeInput) {
        return false;
      }
      return credentialsModeInput.value === "custom";
    }

    function ruleApplies(rule) {
      if (rule.field === usernameInput || rule.field === passwordInput) {
        return isCustomCredentials();
      }
      return true;
    }

    function clearFieldErrors() {
      if (!rules || !rules.length) {
        if (formErrors) {
          formErrors.classList.add("d-none");
          formErrors.textContent = "";
        }
        return;
      }
      rules.forEach(function (rule) {
        rule.field.classList.remove("is-invalid");
        if (rule.errorEl) {
          rule.errorEl.classList.remove("d-block");
        }
      });
      if (formErrors) {
        formErrors.classList.add("d-none");
        formErrors.textContent = "";
      }
    }

    function showFieldErrors() {
      clearFieldErrors();
      var missing = [];

      rules.forEach(function (rule) {
        if (!ruleApplies(rule)) {
          return;
        }
        if (!rule.isValid()) {
          rule.field.classList.add("is-invalid");
          if (rule.errorEl) {
            rule.errorEl.classList.add("d-block");
          }
          missing.push(rule.label);
        }
      });

      if (missing.length && formErrors) {
        formErrors.textContent =
          "Veuillez remplir les champs obligatoires : " + missing.join(", ") + ".";
        formErrors.classList.remove("d-none");
      }

      return missing.length === 0;
    }

    function syncCredentialFieldsState() {
      var custom = isCustomCredentials();
      if (usernameInput) {
        usernameInput.disabled = !custom;
      }
      if (passwordInput) {
        passwordInput.disabled = !custom;
      }
      if (defaultSummaryEl) {
        defaultSummaryEl.classList.toggle("d-none", custom);
      }
      if (showCustomBtn) {
        showCustomBtn.classList.toggle("d-none", custom);
      }
    }

    function setCustomCredentialsVisible(visible) {
      if (!customCredentialsEl || !credentialsModeInput) {
        return;
      }
      if (visible) {
        customCredentialsEl.classList.remove("d-none");
        credentialsModeInput.value = "custom";
      } else {
        customCredentialsEl.classList.add("d-none");
        credentialsModeInput.value = "default";
        if (usernameInput) {
          usernameInput.value = "";
        }
        if (passwordInput) {
          passwordInput.value = "";
        }
      }
      syncCredentialFieldsState();
      clearFieldErrors();
    }

    if (forceCustomCredentials) {
      setCustomCredentialsVisible(true);
    } else {
      setCustomCredentialsVisible(false);
    }

    form.querySelectorAll(".js-toggle-custom-credentials").forEach(function (btn) {
      btn.addEventListener("click", function (event) {
        event.preventDefault();
        setCustomCredentialsVisible(true);
      });
    });

    form.querySelectorAll(".js-toggle-custom-credentials-back").forEach(function (btn) {
      btn.addEventListener("click", function (event) {
        event.preventDefault();
        setCustomCredentialsVisible(false);
      });
    });

    function hostLabel() {
      if (hostSelect && hostSelect.value) {
        var option = hostSelect.options[hostSelect.selectedIndex];
        return option ? option.textContent.trim() : null;
      }
      var hostLabelEl = form.querySelector(".js-backup-host-label");
      return hostLabelEl ? hostLabelEl.textContent.trim() : null;
    }

    function updateSummary() {
      if (!summaryEl) {
        return;
      }
      var lines = [];
      var host = hostLabel();
      if (host) {
        lines.push("Host cible : " + host);
      }
      if (isCustomCredentials() && usernameInput && usernameInput.value.trim()) {
        lines.push("Identifiant API : " + usernameInput.value.trim());
      } else if (!forceCustomCredentials && usernameInput) {
        lines.push("Identifiants : par défaut (serveur)");
      }
      var arborDcs = form.getAttribute("data-arbor-dcs");
      if (!hostSelect && arborDcs) {
        lines.push("DC actifs : " + arborDcs);
      }
      summaryEl.textContent = lines.join(" — ");
    }

    function focusFirstInvalid() {
      var first = form.querySelector(".is-invalid:not([disabled])");
      if (first && typeof first.focus === "function") {
        first.focus();
      }
    }

    function bindClearOnInput(field) {
      if (!field) {
        return;
      }
      var clearIfFixed = function () {
        if (field.classList.contains("is-invalid") && showFieldErrors()) {
          clearFieldErrors();
        }
      };
      field.addEventListener("input", clearIfFixed);
      field.addEventListener("change", function () {
        clearIfFixed();
        updateSummary();
      });
    }

    bindClearOnInput(hostSelect);
    bindClearOnInput(usernameInput);
    bindClearOnInput(passwordInput);

    openBtn.addEventListener("click", function (event) {
      event.preventDefault();
      syncCredentialFieldsState();
      if (!showFieldErrors()) {
        focusFirstInvalid();
        return;
      }
      clearFieldErrors();
      updateSummary();
      if (modal) {
        modal.show();
      }
    });

    if (confirmBtn) {
      confirmBtn.addEventListener("click", function (event) {
        event.preventDefault();
        syncCredentialFieldsState();
        if (!showFieldErrors()) {
          if (modal) {
            modal.hide();
          }
          focusFirstInvalid();
          return;
        }
        openBtn.disabled = true;
        confirmBtn.disabled = true;
        confirmBtn.setAttribute("aria-busy", "true");
        if (modal) {
          modal.hide();
        }
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          form.submit();
        }
      });
    }
  });

  initBackupHistoryPolling();
});

function initBackupHistoryPolling() {
  var panel = document.querySelector(".js-backup-history");
  if (!panel) {
    return;
  }

  var jobsUrl = panel.getAttribute("data-jobs-url");
  if (!jobsUrl) {
    return;
  }

  var tbody = panel.querySelector(".js-backup-history-body");
  var tableWrap = panel.querySelector(".js-backup-history-table");
  var emptyState = panel.querySelector(".js-backup-history-empty");
  var hintEl = document.querySelector(".js-backup-history-hint");
  var pollTimer = null;
  var lastFingerprint = "";

  function statusBadgeClass(status) {
    if (status === "success") {
      return "text-bg-success";
    }
    if (status === "failed") {
      return "text-bg-danger";
    }
    if (status === "running") {
      return "text-bg-warning text-dark";
    }
    return "text-bg-secondary";
  }

  function triggerBadgeClass(trigger) {
    return trigger === "scheduled"
      ? "text-bg-info"
      : "text-bg-light text-dark border";
  }

  function jobsFingerprint(data) {
    if (!data || !data.jobs) {
      return "";
    }
    return data.jobs
      .map(function (job) {
        return [job.id, job.status, job.message, job.started_at].join(":");
      })
      .join("|");
  }

  function renderJobs(data) {
    if (!tbody) {
      return;
    }

    var jobs = data.jobs || [];
    tbody.innerHTML = "";

    jobs.forEach(function (job) {
      var row = document.createElement("tr");
      row.setAttribute("data-job-id", String(job.id));

      var hostHtml =
        job.host && job.host !== "—"
          ? '<code class="small">' + escapeHtml(job.host) + "</code>"
          : "—";

      row.innerHTML =
        '<td class="text-nowrap small ps-4">' +
        escapeHtml(job.started_at) +
        "</td>" +
        '<td><span class="badge rounded-pill ' +
        statusBadgeClass(job.status) +
        '">' +
        escapeHtml(job.status_label) +
        "</span></td>" +
        '<td class="small text-nowrap">' +
        hostHtml +
        "</td>" +
        '<td class="small text-nowrap"><span class="badge rounded-pill ' +
        triggerBadgeClass(job.trigger) +
        '">' +
        escapeHtml(job.trigger_label) +
        "</span></td>" +
        '<td class="small">' +
        escapeHtml(job.username) +
        "</td>" +
        '<td class="small text-break pe-4">' +
        escapeHtml(job.message) +
        "</td>";

      tbody.appendChild(row);
    });

    if (tableWrap) {
      tableWrap.classList.toggle("d-none", jobs.length === 0);
    }
    if (emptyState) {
      emptyState.classList.toggle("d-none", jobs.length > 0);
    }
    if (data.latest_id) {
      panel.setAttribute("data-latest-id", String(data.latest_id));
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showHint(text) {
    if (!hintEl) {
      return;
    }
    hintEl.textContent = text;
    hintEl.classList.remove("d-none");
    window.setTimeout(function () {
      hintEl.classList.add("d-none");
    }, 4000);
  }

  function pollDelayMs(data) {
    var scheduleActive = panel.getAttribute("data-poll-active") === "1";
    if (data && data.has_running) {
      return 10000;
    }
    if (scheduleActive) {
      return 20000;
    }
    return 0;
  }

  function scheduleNextPoll(data) {
    if (pollTimer) {
      window.clearTimeout(pollTimer);
      pollTimer = null;
    }
    var delay = pollDelayMs(data);
    if (!delay) {
      return;
    }
    pollTimer = window.setTimeout(refreshHistory, delay);
  }

  function refreshHistory() {
    fetch(jobsUrl, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        var fingerprint = jobsFingerprint(data);
        if (fingerprint !== lastFingerprint) {
          renderJobs(data);
          if (lastFingerprint) {
            showHint("Historique mis à jour");
          }
          lastFingerprint = fingerprint;
        }
        scheduleNextPoll(data);
      })
      .catch(function () {
        scheduleNextPoll({ has_running: false });
      });
  }

  lastFingerprint = jobsFingerprint({
    jobs: Array.prototype.map.call(
      panel.querySelectorAll("[data-job-id]"),
      function (row) {
        return {
          id: row.getAttribute("data-job-id"),
          status: row.querySelector(".badge") ? row.querySelector(".badge").textContent : "",
          message: row.cells[5] ? row.cells[5].textContent : "",
          started_at: row.cells[0] ? row.cells[0].textContent : "",
        };
      }
    ),
  });

  if (panel.getAttribute("data-poll-active") === "1") {
    scheduleNextPoll({ has_running: false });
  } else if (panel.getAttribute("data-has-running") === "1") {
    scheduleNextPoll({ has_running: true });
  }
}
