#!/bin/bash
# sync_dmd.sh - Automated rsync for TI DLPC900 DMD Controller
# This script synchronizes the local development folder to the remote board.

REMOTE_USER="user"
REMOTE_HOST="REMOTE_HOST"
REMOTE_DEST="~/"
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
