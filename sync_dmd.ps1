# sync_dmd.ps1 - push this working tree to the rig (no git commit/pull needed).
# Sends the git view of the tree: tracked + untracked files, minus .gitignore
# (so .env, .env_pass, runs/, .venv/, tests/, documentation/, __pycache__ never leave).
# Transport is Windows OpenSSH (ssh/scp) + tar; target from .env
# (REMOTE_USER / REMOTE_HOST / REMOTE_DEST). Run from anywhere: .\sync_dmd.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvPath = Join-Path $ScriptDir ".env"

if (-not (Test-Path $EnvPath)) {
    Write-Error ".env not found at $EnvPath (needs REMOTE_USER / REMOTE_HOST / REMOTE_DEST)."
    exit 1
}
Get-Content $EnvPath | ForEach-Object {
    if ($_ -match '^\s*([^#=\s][^=]*)=(.*)$') {
        Set-Variable -Name $matches[1].Trim() -Value $matches[2].Trim().Trim('"').Trim("'") -Scope Script
    }
}
if (-not $REMOTE_USER) { Write-Error "REMOTE_USER not set in .env"; exit 1 }
if (-not $REMOTE_HOST) { Write-Error "REMOTE_HOST not set in .env"; exit 1 }
if (-not $REMOTE_DEST) { $REMOTE_DEST = "~/dmdcontrol/" }
$Remote = "${REMOTE_USER}@${REMOTE_HOST}"
$RemoteTar = "/tmp/dmdcontrol_sync_$PID.tgz"

Push-Location $ScriptDir
$ListFile = Join-Path $env:TEMP "dmdcontrol_sync_files.txt"
$TarFile  = Join-Path $env:TEMP "dmdcontrol_sync.tgz"
try {
    Write-Host "=== Syncing $ScriptDir -> ${Remote}:${REMOTE_DEST} ===" -ForegroundColor Cyan

    # git view of the working tree (tracked + untracked, .gitignore honoured)
    $files = @(git ls-files -co --exclude-standard | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) })
    if ($LASTEXITCODE -ne 0 -or $files.Count -eq 0) { Write-Error "git ls-files failed or returned nothing"; exit 1 }
    [IO.File]::WriteAllText($ListFile, ($files -join "`n"), (New-Object Text.UTF8Encoding $false))
    Write-Host ("{0} files, git: {1}" -f $files.Count, (git describe --always --dirty))

    tar -czf $TarFile -T $ListFile
    if ($LASTEXITCODE -ne 0) { Write-Error "tar failed ($LASTEXITCODE)"; exit $LASTEXITCODE }

    scp -q $TarFile "${Remote}:${RemoteTar}"
    if ($LASTEXITCODE -ne 0) { Write-Error "scp failed ($LASTEXITCODE)"; exit $LASTEXITCODE }

    # extract; unix line endings on the synced text files (dos2unix skips binaries); shell scripts executable
    $remoteCmd = "set -e; mkdir -p ${REMOTE_DEST}; cd ${REMOTE_DEST}; tar -xzf ${RemoteTar}; " +
                 "tar -tzf ${RemoteTar} | grep -v '/`$' | xargs -d '\n' -r dos2unix -q; rm -f ${RemoteTar}; " +
                 "chmod +x scripts/*.sh 2>/dev/null || true; echo synced: `$(pwd)"
    ssh $Remote $remoteCmd
    if ($LASTEXITCODE -ne 0) { Write-Error "remote extract failed ($LASTEXITCODE)"; exit $LASTEXITCODE }

    Write-Host "Done." -ForegroundColor Green
}
finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $ListFile, $TarFile
    Pop-Location
}
