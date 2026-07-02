#!/bin/sh
# Corrige les droits des fichiers Arbor AED dans les dossiers incoming.
#
# Contexte : l'AED dépose souvent des fichiers en 600 (uid 1003) ; Vaultis lit
# et supprime en uid 1000 dans le conteneur.
#
# Au démarrage Docker : appelé par docker/fix-arbor-on-start.sh (root).
# Sur l'hôte (cron) : scripts/fix-arbor-incoming-permissions.sh --env .env

set -eu

ENV_FILE=""
INSIDE_CONTAINER=0
VAULTIS_UID="${VAULTIS_UID:-1000}"
APPLY_ACL=1
DRY_RUN=0

usage() {
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
  echo ""
  echo "Options :"
  echo "  --env FILE              Fichier .env (mode hôte)"
  echo "  --inside-container      Chemins conteneur (/app/arbor/incoming/...)"
  echo "  --vaultis-uid UID       uid Vaultis (défaut : 1000)"
  echo "  --no-acl                Ne pas utiliser setfacl"
  echo "  --dry-run               Afficher sans modifier"
  echo "  -h, --help              Aide"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --env)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    --inside-container)
      INSIDE_CONTAINER=1
      shift
      ;;
    --vaultis-uid)
      VAULTIS_UID="${2:-1000}"
      shift 2
      ;;
    --no-acl)
      APPLY_ACL=0
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Option inconnue : $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "${ENV_FILE}" ] && [ "${INSIDE_CONTAINER}" -eq 0 ]; then
  if [ -f "./.env" ]; then
    ENV_FILE="./.env"
  elif [ -f "../.env" ]; then
    ENV_FILE="../.env"
  fi
fi

_env_val() {
  key="$1"
  if [ -n "${ENV_FILE}" ] && [ -f "${ENV_FILE}" ]; then
    # shellcheck disable=SC2155
    local val
    val="$(grep -E "^[[:space:]]*${key}=" "${ENV_FILE}" | tail -n 1 | cut -d= -f2- | tr -d '\r' | sed -e 's/^["'\'']//' -e 's/["'\'']$//')"
    printf '%s' "${val}"
    return 0
  fi
  eval "printf '%s' \"\${${key}:-}\""
}

_dc_is_active() {
  dc="$1"
  active="$(_env_val ARBOR_AED_ACTIVE_DCS)"
  if [ -z "${active}" ]; then
    return 1
  fi
  printf '%s' "${active}" | tr ',' '\n' | tr -d ' ' | tr '[:lower:]' '[:upper:]' | grep -Fx "${dc}" >/dev/null
}

_container_dir_for_dc() {
  dc="$1"
  case "${dc}" in
    DC01)
      path="$(_env_val ARBOR_AED_SOURCE_DIR_DC01)"
      [ -n "${path}" ] || path="/app/arbor/incoming/dc01"
      ;;
    DC02)
      path="$(_env_val ARBOR_AED_SOURCE_DIR_DC02)"
      [ -n "${path}" ] || path="/app/arbor/incoming/dc02"
      ;;
    *)
      return 1
      ;;
  esac
  printf '%s' "${path}"
}

_collect_dirs() {
  dirs=""
  if [ "${INSIDE_CONTAINER}" -eq 1 ]; then
    for dc in DC01 DC02; do
      if ! _dc_is_active "${dc}"; then
        continue
      fi
      path="$(_container_dir_for_dc "${dc}")" || continue
      dirs="${dirs} ${path}"
    done
  else
    for key in ARBOR_AED_SOURCE_HOST_DC01 ARBOR_AED_SOURCE_HOST_DC02; do
      path="$(_env_val "${key}")"
      if [ -n "${path}" ]; then
        dirs="${dirs} ${path}"
      fi
    done
  fi
  printf '%s\n' ${dirs} | awk '!seen[$0]++ && length($0)>0'
}

_run() {
  if [ "${DRY_RUN}" -eq 1 ]; then
    printf '[dry-run] '
    printf '%s ' "$@"
    printf '\n'
  else
    "$@"
  fi
}

_fix_dir() {
  dir="$1"
  if [ ! -d "${dir}" ]; then
    echo "Ignoré (introuvable) : ${dir}"
    return 0
  fi

  echo "Arbor permissions : ${dir}"

  _run find "${dir}" -type d -exec chmod 2775 {} + 2>/dev/null || true
  _run find "${dir}" -type f -name 'arbor-backup-*' -exec chmod 664 {} + 2>/dev/null || true

  if [ "${APPLY_ACL}" -eq 1 ] && command -v setfacl >/dev/null 2>&1; then
    _run setfacl -R -m "u:${VAULTIS_UID}:rwX" "${dir}" 2>/dev/null || true
    _run setfacl -R -d -m "u:${VAULTIS_UID}:rwX" "${dir}" 2>/dev/null || true
    echo "  ACL appliquée pour uid ${VAULTIS_UID}"
  elif [ "${APPLY_ACL}" -eq 1 ]; then
    echo "  setfacl absent — chmod seul"
  fi

  unreadable=0
  for f in "${dir}"/arbor-backup-*; do
    [ -e "${f}" ] || continue
    [ -f "${f}" ] || continue
    readable=0
    if [ "$(id -u)" -eq 0 ] && command -v gosu >/dev/null 2>&1; then
      if gosu "${VAULTIS_UID}" test -r "${f}"; then
        readable=1
      fi
    elif [ -r "${f}" ]; then
      readable=1
    fi
    if [ "${readable}" -eq 0 ]; then
      unreadable=$((unreadable + 1))
    fi
  done
  if [ "${unreadable}" -gt 0 ]; then
    echo "  Attention : ${unreadable} fichier(s) arbor-backup-* encore non lisibles par uid ${VAULTIS_UID}" >&2
    return 1
  fi
  echo "  OK"
  return 0
}

main() {
  if [ "$(id -u)" -ne 0 ] && [ "${INSIDE_CONTAINER}" -eq 1 ]; then
    echo "Arbor permissions : ignoré (nécessite root dans le conteneur)." >&2
    exit 0
  fi

  if [ "$(id -u)" -ne 0 ] && [ "${INSIDE_CONTAINER}" -eq 0 ]; then
    echo "Attention : exécution sans root — chmod/ACL peut échouer sur fichiers uid 1003." >&2
  fi

  dirs="$(_collect_dirs)"
  if [ -z "${dirs}" ]; then
    if [ "${INSIDE_CONTAINER}" -eq 1 ]; then
      echo "Arbor permissions : aucun DC actif (ARBOR_AED_ACTIVE_DCS vide)."
      exit 0
    fi
    echo "Aucun dossier Arbor configuré (ARBOR_AED_SOURCE_HOST_DC*)." >&2
    exit 1
  fi

  failed=0
  for dir in ${dirs}; do
    if ! _fix_dir "${dir}"; then
      failed=1
    fi
  done

  exit "${failed}"
}

main "$@"
