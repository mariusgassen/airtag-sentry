#!/bin/sh
set -eu

# Older images ran as root, leaving /app/data (account.json,
# pyicloud_session/*.session) owned by root inside existing Docker volumes.
# Docker does not re-chown populated volumes when an image switches to a
# non-root user, so fix ownership on startup before dropping to appuser.
if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/data
    chown -R appuser:appuser /app/data
    export HOME=/home/appuser
    exec setpriv --reuid=appuser --regid=appuser --clear-groups -- python -m airtag_sentry "$@"
fi

exec python -m airtag_sentry "$@"
