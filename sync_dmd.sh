#!/bin/bash
# sync_dmd.sh - Automated rsync for TI DLPC900 DMD Controller
# This script synchronizes the local development folder to the remote board.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    set -a; . "$ENV_FILE"; set +a
else
    echo "Error: $ENV_FILE not found. Copy .env.example to .env and fill in REMOTE_USER / REMOTE_HOST / REMOTE_DEST."
    exit 1
fi

: "${REMOTE_USER:?REMOTE_USER not set in .env}"
: "${REMOTE_HOST:?REMOTE_HOST not set in .env}"
: "${REMOTE_DEST:=~/}"
EXCLUDE_FILE=".sync-exclude"

echo "=== Syncing DMD Source Code to ${REMOTE_HOST} ==="

if [ -f "$EXCLUDE_FILE" ]; then
    rsync -avz --exclude-from="$EXCLUDE_FILE" ./ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DEST}"
else
    rsync -avz ./ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DEST}"
fi

echo "Converting line endings to Unix format..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" "cd ${REMOTE_DEST} && dos2unix *.sh *.py"

echo "Done."
