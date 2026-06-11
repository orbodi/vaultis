#!/bin/sh
# Vérifie que les dossiers de sauvegarde bind-mountés sont inscriptibles (appuser uid 1000).

_host_path_for() {
  explicit_host_dir="$1"
  container_subpath="$2"
  default_relative="$3"
  if [ -n "${explicit_host_dir}" ]; then
    echo "${explicit_host_dir}"
    return
  fi
  if [ -n "${VAULTIS_HOST_DATA_DIR}" ]; then
    echo "${VAULTIS_HOST_DATA_DIR}${container_subpath}"
    return
  fi
  echo "${default_relative}"
}

_check_writable_dir() {
  container_dir="$1"
  label="$2"
  host_dir="$3"
  mkdir -p "${container_dir}" 2>/dev/null || true
  probe="${container_dir}/.vaultis_write_test"
  if ! ( : > "${probe}" ) 2>/dev/null; then
    echo "ERREUR: écriture impossible dans ${container_dir} (${label})." >&2
    echo "Bind mount attendu : ${host_dir} → ${container_dir}" >&2
    echo "Sur le serveur Linux hôte (appuser = uid 1000 dans le conteneur) :" >&2
    echo "  mkdir -p ${host_dir}" >&2
    echo "  chown -R 1000:1000 ${host_dir}" >&2
    echo "  chmod -R 775 ${host_dir}" >&2
    exit 1
  fi
  rm -f "${probe}"
}

_check_writable_dir \
  "${NITROKEY_BACKUP_ROOT:-/app/data/backups/nitrokey}" \
  "Nitrokey" \
  "$(_host_path_for "" "/backups/nitrokey" "./data/backups/nitrokey")"

_check_writable_dir \
  "${F5_BACKUP_ROOT:-/app/data/backups/f5}" \
  "F5" \
  "$(_host_path_for "${F5_BACKUP_HOST_DIR}" "/backups/f5" "./data/backups/f5")"

_check_writable_dir \
  "${F5_DN1_BACKUP_ROOT:-/app/data/backups/f5-dn1}" \
  "F5-DN1" \
  "$(_host_path_for "${F5_DN1_BACKUP_HOST_DIR}" "/backups/f5-dn1" "./data/backups/f5-dn1")"

_check_writable_dir \
  "${F5_DN2_BACKUP_ROOT:-/app/data/backups/f5-dn2}" \
  "F5-DN2" \
  "$(_host_path_for "${F5_DN2_BACKUP_HOST_DIR}" "/backups/f5-dn2" "./data/backups/f5-dn2")"
