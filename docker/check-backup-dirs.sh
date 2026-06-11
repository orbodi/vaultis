#!/bin/sh
# Vérifie que les dossiers de sauvegarde bind-mountés sont inscriptibles (appuser uid 1000).

_check_writable_dir() {
  dir="$1"
  label="$2"
  host_hint="$3"
  mkdir -p "${dir}" 2>/dev/null || true
  probe="${dir}/.vaultis_write_test"
  if ! ( : > "${probe}" ) 2>/dev/null; then
    echo "ERREUR: écriture impossible dans ${dir} (${label})." >&2
    echo "Sur le serveur Linux hôte (appuser = uid 1000 dans le conteneur) :" >&2
    echo "  mkdir -p ${host_hint}" >&2
    echo "  chown -R 1000:1000 ${host_hint}" >&2
    echo "  chmod -R 775 ${host_hint}" >&2
    exit 1
  fi
  rm -f "${probe}"
}

_host_hint() {
  container_path="$1"
  default_host_path="$2"
  case "${container_path}" in
    /app/data/*)
      if [ -n "${VAULTIS_HOST_DATA_DIR}" ]; then
        echo "${VAULTIS_HOST_DATA_DIR}${container_path#/app/data}"
      else
        echo "${default_host_path}"
      fi
      ;;
    *)
      echo "${default_host_path}"
      ;;
  esac
}

_check_writable_dir \
  "${NITROKEY_BACKUP_ROOT:-/app/data/backups/nitrokey}" \
  "Nitrokey" \
  "$(_host_hint "${NITROKEY_BACKUP_ROOT:-/app/data/backups/nitrokey}" "./data/backups/nitrokey")"

_check_writable_dir \
  "${F5_BACKUP_ROOT:-/app/data/backups/f5}" \
  "F5" \
  "${F5_BACKUP_HOST_DIR:-$(_host_hint "/app/data/backups/f5" "./data/backups/f5")}"

_check_writable_dir \
  "${F5_DN1_BACKUP_ROOT:-/app/data/backups/f5-dn1}" \
  "F5-DN1" \
  "${F5_DN1_BACKUP_HOST_DIR:-$(_host_hint "/app/data/backups/f5-dn1" "./data/backups/f5-dn1")}"

_check_writable_dir \
  "${F5_DN2_BACKUP_ROOT:-/app/data/backups/f5-dn2}" \
  "F5-DN2" \
  "${F5_DN2_BACKUP_HOST_DIR:-$(_host_hint "/app/data/backups/f5-dn2" "./data/backups/f5-dn2")}"
