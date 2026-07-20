#!/bin/bash
# run_camera_sync_check.sh
# Paired DLPC900 runner for DVXplorer sync-check capture.
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/dmd_shell_common.sh"

dmd_parse_dmd_config_arg "$@"


echo "=== Paired DLPC900 DP Wake for camera sync-check ==="
dmd_wake_configured_pair "$SCRIPT_DIR" "${DMD_CONFIG_ARGS[@]}"

dmd_wait_for_hotplug "Xorg and GPU to detect both DP hotplug events" 2

echo "=== Launching Camera Sync Check ==="
dmd_run_xinit_python_module "$SCRIPT_DIR" dmdcontrol camera sync-check -- "$@"
