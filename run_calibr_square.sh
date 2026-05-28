#!/bin/bash
# Interactive calibration-square launcher.
# This is intentionally separate from run_dmd.sh so normal DMD runs keep their
# original stdin/sudo/xinit behavior.
set -e

echo "=== DLPC900 Calibration Square ==="
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/lib/dmd_shell_common.sh"

CONTROL_FILE="$(dmd_create_calibr_square_control_file)"
DMD_CALIBR_CONTROL_PID=""

cleanup() {
    dmd_stop_calibr_square_control_reader "$DMD_CALIBR_CONTROL_PID"
    rm -f "$CONTROL_FILE"
}
trap cleanup EXIT

dmd_wake_with_args "$SCRIPT_DIR" "$@"

dmd_wait_for_hotplug "Xorg and GPU to detect the DP hotplug event"

echo "=== Launching Interactive Calibration Square ==="
dmd_start_calibr_square_control_reader "$CONTROL_FILE" "dmdcontrol single run"

dmd_run_xinit "$SCRIPT_DIR" "$SCRIPT_DIR/scripts/xinit/xinitrc_dmd.sh" \
    --test calibr-square \
    --calibr-square-control-file "$CONTROL_FILE" \
    --runtime-seconds 0 \
    "$@"
