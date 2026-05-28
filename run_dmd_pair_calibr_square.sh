#!/bin/bash
# Interactive paired calibration-square + static B-dot launcher.
set -e

echo "=== Paired DLPC900 Calibration Square + B Dot ==="
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/lib/dmd_shell_common.sh"

dmd_parse_dmd_config_arg "$@"

if dmd_has_flag --dry-run-timing "$@"; then
    echo "=== Paired calibration dry-run timing (no DP wake, no X, no sudo) ==="
    dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol pair calibrate "$@"
fi

CONTROL_FILE="$(dmd_create_calibr_square_control_file)"
DMD_CALIBR_CONTROL_PID=""

cleanup() {
    dmd_stop_calibr_square_control_reader "$DMD_CALIBR_CONTROL_PID"
    rm -f "$CONTROL_FILE"
}
trap cleanup EXIT

echo "=== Paired DLPC900 DP Wake ==="
dmd_wake_configured_dmd "$SCRIPT_DIR" A "${DMD_CONFIG_ARGS[@]}"
dmd_wake_configured_dmd "$SCRIPT_DIR" B "${DMD_CONFIG_ARGS[@]}"

dmd_wait_for_hotplug "Xorg and GPU to detect both DP hotplug events"

echo "=== Launching Interactive Paired Calibration Square + B Dot ==="
dmd_start_calibr_square_control_reader "$CONTROL_FILE" "dmdcontrol pair run"

dmd_run_xinit "$SCRIPT_DIR" "$SCRIPT_DIR/scripts/xinit/xinitrc_dmd_pair.sh" \
    --test a-calibr-square-b-dot \
    --a-calibr-square-control-file "$CONTROL_FILE" \
    --runtime-seconds 0 \
    "$@"
