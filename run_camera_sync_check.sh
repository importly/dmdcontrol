#!/bin/bash
# run_camera_sync_check.sh
# Paired DLPC900 runner for DVXplorer sync-check capture.
set -e # idk

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" # not sure
source "$SCRIPT_DIR/scripts/lib/dmd_shell_common.sh" # get all the functions from shell common.sh

dmd_parse_dmd_config_arg "$@" # parse for dmd commands? there i looked inside and it was dmd config stuff but like I dont think i even use that

if dmd_has_flag --dry-run "$@"; then # check for try run
    echo "=== Camera sync-check dry-run (no DP wake, no X, no sudo) ==="
    dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol camera sync-check "$@"
    exit 0
fi

echo "=== Paired DLPC900 DP Wake for camera sync-check ==="
dmd_wake_configured_dmd "$SCRIPT_DIR" A "${DMD_CONFIG_ARGS[@]}" # wake dmds
dmd_wake_configured_dmd "$SCRIPT_DIR" B "${DMD_CONFIG_ARGS[@]}"

dmd_wait_for_hotplug "Xorg and GPU to detect both DP hotplug events" # do setup for gpu

echo "=== Launching Camera Sync Check (via scripts/xinit/xinitrc_camera_sync_check.sh wrapper) ==="
dmd_run_xinit "$SCRIPT_DIR" "$SCRIPT_DIR/scripts/xinit/xinitrc_camera_sync_check.sh" "$@" # then run xinit but i didnt understand why the xinitrc script is not just continuing here...
