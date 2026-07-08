#!/bin/bash
# run_dmd_pair_capture.sh
# Paired DMD + camera capture hardware runner.
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/dmd_shell_common.sh"

dmd_parse_dmd_config_arg "$@"


echo "=== Paired Camera Capture DLPC900 DP Wake ==="
dmd_wake_configured_dmd "$SCRIPT_DIR" A "${DMD_CONFIG_ARGS[@]}"
dmd_wake_configured_dmd "$SCRIPT_DIR" B "${DMD_CONFIG_ARGS[@]}"

dmd_wait_for_hotplug "Xorg and GPU to detect both DP hotplug events"

echo "=== Launching Paired Camera Capture ==="
dmd_run_xinit_python_module "$SCRIPT_DIR" pair dmdcontrol camera pair-capture -- "$@"
