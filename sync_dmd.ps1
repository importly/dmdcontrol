# sync_dmd.ps1 - Windows helper for TI DLPC900 DMD Controller Sync
# This script uses WSL's rsync to sync the local folder to a dedicated remote folder.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvPath = Join-Path $ScriptDir ".env"

if (-not (Test-Path $EnvPath)) {
    Write-Error ".env not found at $EnvPath. Copy .env.example to .env and fill in REMOTE_USER / REMOTE_HOST / REMOTE_DEST."
    exit 1
}

Get-Content $EnvPath | ForEach-Object {
    if ($_ -match '^\s*([^#=\s][^=]*)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"').Trim("'")
        Set-Variable -Name $name -Value $value -Scope Script
    }
}

if (-not $REMOTE_USER) { Write-Error "REMOTE_USER not set in .env"; exit 1 }
if (-not $REMOTE_HOST) { Write-Error "REMOTE_HOST not set in .env"; exit 1 }
if (-not $REMOTE_DEST) { $REMOTE_DEST = "~/dmd_project/" }
$EXCLUDE_FILE = ".sync-exclude"

Write-Host "=== Syncing DMD Source Code via WSL rsync to $REMOTE_HOST ($REMOTE_DEST) ===" -ForegroundColor Cyan

if (Test-Path $EXCLUDE_FILE) {
    wsl rsync -avz --exclude-from=".sync-exclude" -e "ssh" ./ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DEST}"
} else {
    wsl rsync -avz -e "ssh" ./ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DEST}"
}

Write-Host "Converting line endings to Unix format..." -ForegroundColor Cyan
wsl ssh "${REMOTE_USER}@${REMOTE_HOST}" "cd ${REMOTE_DEST} && dos2unix *.sh *.py"

Write-Host "Done." -ForegroundColor Green
