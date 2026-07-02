#!/bin/sh
# Wrapper hôte → script Docker (mode --env pour chemins ARBOR_AED_SOURCE_HOST_*).
set -eu
ROOT="$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
exec "${ROOT}/docker/fix-arbor-incoming-permissions.sh" "$@"
