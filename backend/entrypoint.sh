#!/bin/sh
# Fly.io volumes (and some other hosts) mount /data owned by root. Fix ownership
# as root, then drop to the unprivileged user before starting the app.
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /data
  chown -R appuser:appuser /data
  exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"
fi
exec "$@"
