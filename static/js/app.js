/**
 * Sauvegarde : validation avec messages visibles, puis modal de confirmation.
 */
document.addEventListener("DOMContentLoaded", function () {
  var modalEl = document.getElementById("backupConfirmModal");
  if (!modalEl) {
    return;
  }

  if (modalEl.parentElement !== document.body) {
    document.body.appendChild(modalEl);
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

    function clearFieldErrors() {
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
      } else if (!forceCustomCredentials) {
        lines.push("Identifiants : par défaut (serveur)");
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
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          form.submit();
        }
        if (modal) {
          modal.hide();
        }
      });
    }
  });
});
