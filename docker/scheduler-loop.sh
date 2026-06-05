#!/bin/sh
set -e

INTERVAL="${BACKUP_SCHEDULER_INTERVAL_SECONDS:-60}"

echo "Planificateur Vaultis — intervalle ${INTERVAL}s (TIME_ZONE=${DJANGO_TIME_ZONE:-UTC})"

while true; do
  python manage.py run_backup_schedules || echo "run_backup_schedules: erreur (voir logs)."
  sleep "${INTERVAL}"
done
