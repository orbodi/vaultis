/** vaultis app.js v20260605 */
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

  function showBackupProgress(options) {
    if (!progressOverlay) {
      return;
    }

    clearProgressTimers();
    progressValue = 0;
    setProgressValue(0);

    if (progressEquipment && options.equipmentName) {
      progressEquipment.textContent = options.equipmentName;
    }

    var messages = options.isArbor ? arborStatusMessages : defaultStatusMessages;
    startStatusRotation(messages);

    progressOverlay.classList.remove("d-none");
    progressOverlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("backup-in-progress");

    progressTimer = window.setInterval(function () {
      var remaining = 92 - progressValue;
      var step = remaining > 30 ? 1.2 : remaining > 10 ? 0.35 : 0.08;
      setProgressValue(progressValue + step);
    }, 900);

    window.addEventListener("beforeunload", preventUnloadWhileBackup);
  }

  function preventUnloadWhileBackup(event) {
    event.preventDefault();
    event.returnValue = "";
  }

  var modalEl = document.getElementById("backupConfirmModal");
  if (!modalEl) {
    return;
  }

  if (modalEl.parentElement !== document.body) {
    document.body.appendChild(modalEl);
  }

  if (progressOverlay && progressOverlay.parentElement !== document.body) {
    document.body.appendChild(progressOverlay);
  }

  var modal =
    typeof bootstrap !== "undefined"
      ? bootstrap.Modal.getOrCreateInstance(modalEl)
      : null;

  document.querySelectorAll(".js-backup-form").forEach(function (form) {
    var openBtn = form.querySelector(".js-backup-open");
    if (!openBtn) {
      return;
    }

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
    var equipmentTitle = document.querySelector(".app-page-title");
    var isArborForm = Boolean(form.getAttribute("data-arbor-dcs"));

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

        showBackupProgress({
          equipmentName: equipmentTitle ? equipmentTitle.textContent.trim() : "",
          isArbor: isArborForm,
        });

        if (modal) {
          modal.hide();
        }

        window.setTimeout(function () {
          if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
          } else {
            form.submit();
          }
        }, 120);
      });
    }
  });

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
});
