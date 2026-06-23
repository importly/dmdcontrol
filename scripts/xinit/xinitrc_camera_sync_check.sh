#!/bin/bash
# xinitrc_camera_sync_check.sh
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$REPO_ROOT/scripts/lib/dmd_shell_common.sh"
source "$REPO_ROOT/scripts/lib/dmd_x11_common.sh"

echo "=== xinitrc_camera_sync_check: Configuring one spanning X screen ==="
sleep 1

dmd_parse_dmd_config_arg "$@"

A_OUTPUT="$(dmd_config_field "$REPO_ROOT" A xrandr_output "${DMD_CONFIG_FIELD_ARGS[@]}")"
B_OUTPUT="$(dmd_config_field "$REPO_ROOT" B xrandr_output "${DMD_CONFIG_FIELD_ARGS[@]}")"

if [ -z "$A_OUTPUT" ] || [ -z "$B_OUTPUT" ]; then
    echo "[ERROR] DMD A and B must both define xrandr_output in dmd_devices.json."
    exit 1
fi

dmd_x11_require_connected "$B_OUTPUT" "B"
dmd_x11_require_connected "$A_OUTPUT" "A"

echo "Pair outputs: B=$B_OUTPUT at +0+0, A=$A_OUTPUT at +1920+0"

dmd_x11_define_raw_modes "$B_OUTPUT" "$A_OUTPUT"
TARGET_MODE="$DMD_MODE_60"

echo "Applying paired custom modeline: $TARGET_MODE"
dmd_x11_apply_pair_mode "$B_OUTPUT" "$A_OUTPUT" "$TARGET_MODE"

echo "--- xrandr verification ---"
xrandr --query
dmd_x11_verify_pair_layout "$B_OUTPUT" "$A_OUTPUT"

echo "=== Launching dmdcontrol camera sync-check ==="
dmd_exec_python_module "$REPO_ROOT" dmdcontrol camera sync-check "$@"
