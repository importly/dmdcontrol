# sync_dmd.ps1 - Windows helper for TI DLPC900 DMD Controller Sync
# This script uses WSL's rsync to sync the local folder to a dedicated remote folder.

$REMOTE_USER = "user"
$REMOTE_HOST = "REMOTE_HOST"
$REMOTE_DEST = "~/dmd_project/"
$EXCLUDE_FILE = ".sync-exclude"

Write-Host "=== Syncing DMD Source Code via WSL rsync to $REMOTE_HOST (dmd_project folder) ===" -ForegroundColor Cyan

# Use wsl to execute the rsync command
# The path must be converted to wsl format
if (Test-Path $EXCLUDE_FILE) {
    wsl rsync -avz --exclude-from=".sync-exclude" -e "ssh" ./ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DEST}"
} else {
    wsl rsync -avz -e "ssh" ./ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DEST}"
}

Write-Host "Done." -ForegroundColor Green
