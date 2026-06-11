#!/bin/sh
# Vérifie que les dossiers de sauvegarde bind-mountés sont inscriptibles (appuser uid 1000).

_check_writable_dir() {
  dir="$1"
  label="$2"
  mkdir -p "${dir}" 2>/dev/null || true
  probe="${dir}/.vaultis_write_test"
  if ! ( : > "${probe}" ) 2>/dev/null; then
    echo "ERREUR: écriture impossible dans ${dir} (${label})." >&2
    echo "Sur l'hôte (appuser = uid 1000 dans le conteneur) :" >&2
    echo "  mkdir -p /chemin/hôte/backups/f5" >&2
    echo "  chown -R 1000:1000 /chemin/hôte/backups/f5" >&2
    echo "  chmod -R 775 /chemin/hôte/backups/f5" >&2
    exit 1
  fi
  rm -f "${probe}"
}

_check_writable_dir "${NITROKEY_BACKUP_ROOT:-/app/data/backups/nitrokey}" "Nitrokey"
_check_writable_dir "${F5_BACKUP_ROOT:-/app/data/backups/f5}" "F5"
_check_writable_dir "${F5_DN1_BACKUP_ROOT:-/app/data/backups/f5-dn1}" "F5-DN1"
_check_writable_dir "${F5_DN2_BACKUP_ROOT:-/app/data/backups/f5-dn2}" "F5-DN2"
