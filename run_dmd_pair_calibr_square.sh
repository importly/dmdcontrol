#!/bin/bash
# Interactive paired calibration-square + static B-dot launcher.
set -e

echo "=== Paired DLPC900 Calibration Square + B Dot ==="
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/dmd_shell_common.sh"

dmd_parse_dmd_config_arg "$@"


CONTROL_FILE="$(dmd_create_calibr_square_control_file)"
DMD_CALIBR_CONTROL_PID=""

cleanup() {
    dmd_stop_calibr_square_control_reader "$DMD_CALIBR_CONTROL_PID"
    rm -f "$CONTROL_FILE"
}
trap cleanup EXIT

echo "=== Paired DLPC900 DP Wake ==="
dmd_wake_configured_pair "$SCRIPT_DIR" "${DMD_CONFIG_ARGS[@]}"

dmd_wait_for_hotplug "Xorg and GPU to detect both DP hotplug events" 2

echo "=== Launching Interactive Paired Calibration Square + B Dot ==="
dmd_start_calibr_square_control_reader "$CONTROL_FILE" "dmdcontrol pair calibrate"

dmd_run_xinit_python_module "$SCRIPT_DIR" pair dmdcontrol pair calibrate -- \
    --test a-calibr-square-b-dot \
    --a-calibr-square-control-file "$CONTROL_FILE" \
    --runtime-seconds 0 \
    "$@"
