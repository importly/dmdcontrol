#!/usr/bin/env bash
# run_dmd_preview_server.sh
# Starts the offline/live DMD preview server with the lab default bind.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/lib/dmd_shell_common.sh"

dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol preview serve --host 0.0.0.0 --port 8080 "$@"
