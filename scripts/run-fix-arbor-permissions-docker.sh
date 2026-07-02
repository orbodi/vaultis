#!/bin/sh
# Lance la correction des droits Arbor via le conteneur web (root → bind mount hôte).
set -eu
cd "$(dirname "$0")/.."
docker compose exec -u root web /app/docker/fix-arbor-incoming-permissions.sh --inside-container "$@"
