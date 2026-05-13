/**
 * Comportements légers côté navigateur (confirmations, etc.).
 */
(function () {
  document.querySelectorAll(".js-backup-form").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm("Lancer la sauvegarde pour cet équipement ?")) {
        e.preventDefault();
      }
    });
  });
})();
