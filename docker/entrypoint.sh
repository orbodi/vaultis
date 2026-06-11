#!/bin/sh
set -e

. /app/docker/check-backup-dirs.sh

if [ -n "${DATABASE_URL}${POSTGRES_HOST}" ]; then
  echo "Attente de PostgreSQL…"
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

python manage.py migrate --noinput
python manage.py recover_stale_backup_jobs --minutes "${BACKUP_JOB_STALE_MINUTES:-30}"
python manage.py collectstatic --noinput --clear

static_count=$(find /app/staticfiles -type f 2>/dev/null | wc -l)
echo "Fichiers statiques collectés : ${static_count}"
if [ "${static_count}" -lt 5 ]; then
  echo "ERREUR: collectstatic incomplet (bootstrap/css/js manquants)." >&2
  exit 1
fi

PORT="${WEB_PORT:-8010}"
echo "Démarrage de l'application sur le port ${PORT}…"

if [ "${DJANGO_DEBUG}" = "true" ] || [ "${DJANGO_DEBUG}" = "1" ]; then
  exec python manage.py runserver "0.0.0.0:${PORT}"
fi

exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-7200}"
