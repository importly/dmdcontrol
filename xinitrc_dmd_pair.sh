#!/bin/bash
# xinitrc_dmd_pair.sh
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/dmd_shell_common.sh"
source "$SCRIPT_DIR/dmd_x11_common.sh"

echo "=== xinitrc_dmd_pair: Configuring one spanning X screen ==="
sleep 1

dmd_parse_dmd_config_arg "$@"
dmd_parse_hz_arg "" "$@"

A_OUTPUT="$(dmd_config_field "$SCRIPT_DIR" A xrandr_output "${DMD_CONFIG_FIELD_ARGS[@]}")"
B_OUTPUT="$(dmd_config_field "$SCRIPT_DIR" B xrandr_output "${DMD_CONFIG_FIELD_ARGS[@]}")"
A_HZ="$(dmd_config_field "$SCRIPT_DIR" A target_hz "${DMD_CONFIG_FIELD_ARGS[@]}")"
B_HZ="$(dmd_config_field "$SCRIPT_DIR" B target_hz "${DMD_CONFIG_FIELD_ARGS[@]}")"

if [ -z "$A_OUTPUT" ] || [ -z "$B_OUTPUT" ]; then
    echo "[ERROR] DMD A and B must both define xrandr_output in dmd_devices.json."
    exit 1
fi
TARGET_HZ="$DMD_TARGET_HZ"
if [ -z "$TARGET_HZ" ]; then
    if [ -n "$A_HZ" ] && [ -n "$B_HZ" ] && [ "$A_HZ" != "$B_HZ" ]; then
        echo "[ERROR] DMD A and B target_hz values differ ($A_HZ vs $B_HZ). Pass --hz explicitly or fix dmd_devices.json."
        exit 1
    fi
    TARGET_HZ="${A_HZ:-${B_HZ:-60}}"
fi

dmd_x11_require_connected "$B_OUTPUT" "B"
dmd_x11_require_connected "$A_OUTPUT" "A"

echo "Pair outputs: B=$B_OUTPUT at +0+0, A=$A_OUTPUT at +1920+0"

dmd_x11_define_raw_modes "$B_OUTPUT" "$A_OUTPUT"
TARGET_MODE="$(dmd_x11_target_mode_for_hz "$TARGET_HZ")"

echo "Applying paired custom modeline: $TARGET_MODE"
dmd_x11_apply_pair_mode "$B_OUTPUT" "$A_OUTPUT" "$TARGET_MODE"

echo "--- xrandr verification ---"
xrandr --query
dmd_x11_verify_pair_layout "$B_OUTPUT" "$A_OUTPUT"

echo "=== Launching dmdcontrol pair run ==="
dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol pair run "$@"
