#!/bin/sh
set -e

INTERVAL="${BACKUP_SCHEDULER_INTERVAL_SECONDS:-60}"

if [ -n "${DATABASE_URL}${POSTGRES_HOST}" ]; then
  echo "Planificateur — attente de PostgreSQL…"
  until python -c "
import os, sys
url = os.environ.get('DATABASE_URL', '').strip()
if not url:
    user = os.environ.get('POSTGRES_USER', 'vaultis')
    password = os.environ.get('POSTGRES_PASSWORD', '')
    host = os.environ.get('POSTGRES_HOST', 'db')
    port = os.environ.get('POSTGRES_PORT', '5432')
    name = os.environ.get('POSTGRES_DB', 'vaultis')
    url = f'postgresql://{user}:{password}@{host}:{port}/{name}'
import psycopg
try:
    psycopg.connect(url).close()
except Exception:
    sys.exit(1)
"; do
    sleep 1
  done
fi

. /app/docker/check-backup-dirs.sh

echo "Planificateur — migrations Django…"
python manage.py migrate --noinput

echo "Planificateur Vaultis — intervalle ${INTERVAL}s (TIME_ZONE=${DJANGO_TIME_ZONE:-UTC})"

while true; do
  python manage.py run_backup_schedules || echo "run_backup_schedules: erreur (voir logs)."
  sleep "${INTERVAL}"
done
