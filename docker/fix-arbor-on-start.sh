#!/bin/sh
# Lance la correction des droits Arbor au démarrage du conteneur (root requis).
set -eu

case "${ARBOR_AED_FIX_PERMISSIONS_ON_START:-true}" in
  false|0|no|off|FALSE|NO|OFF)
    echo "Arbor permissions au démarrage : désactivé (ARBOR_AED_FIX_PERMISSIONS_ON_START)."
    exit 0
    ;;
esac

if [ -z "${ARBOR_AED_ACTIVE_DCS:-}" ]; then
  echo "Arbor permissions au démarrage : ignoré (ARBOR_AED_ACTIVE_DCS vide)."
  exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Arbor permissions au démarrage : ignoré (conteneur non root)." >&2
  exit 0
fi

echo "Arbor permissions au démarrage…"
if /app/docker/fix-arbor-incoming-permissions.sh --inside-container; then
  echo "Arbor permissions au démarrage : terminé."
else
  echo "Attention : correction des droits Arbor incomplète (la sauvegarde peut échouer)." >&2
fi
