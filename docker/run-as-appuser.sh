#!/bin/sh
# Helpers pour exécuter l'application en appuser (uid 1000) depuis un entrypoint root.

run_as_appuser() {
  if [ "$(id -u)" -eq 0 ]; then
    gosu appuser "$@"
  else
    "$@"
  fi
}

exec_as_appuser() {
  if [ "$(id -u)" -eq 0 ]; then
    exec gosu appuser "$@"
  else
    exec "$@"
  fi
}
