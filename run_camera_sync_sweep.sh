#!/bin/bash
# run_camera_sync_sweep.sh
# Paired DLPC900 runner for a persistent-camera DVXplorer sync-check sweep.
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/lib/dmd_shell_common.sh"

dmd_parse_dmd_config_arg "$@"

if dmd_has_flag --dry-run "$@"; then
    echo "=== Camera sync-sweep dry-run (no DP wake, no X, no sudo) ==="
    dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol camera sync-sweep "$@"
    exit 0
fi

echo "=== Paired DLPC900 DP Wake for camera sync-sweep ==="
dmd_wake_configured_dmd "$SCRIPT_DIR" A "${DMD_CONFIG_ARGS[@]}"
dmd_wake_configured_dmd "$SCRIPT_DIR" B "${DMD_CONFIG_ARGS[@]}"

dmd_wait_for_hotplug "Xorg and GPU to detect both DP hotplug events"

echo "=== Launching Camera Sync Sweep (via scripts/xinit/xinitrc_camera_sync_sweep.sh wrapper) ==="
dmd_run_xinit "$SCRIPT_DIR" "$SCRIPT_DIR/scripts/xinit/xinitrc_camera_sync_sweep.sh" "$@"
