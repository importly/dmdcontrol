#!/bin/bash
# xinitrc_dmd.sh
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/dmd_shell_common.sh"
source "$SCRIPT_DIR/dmd_x11_common.sh"

echo "=== xinitrc_dmd: Configuring display for NVIDIA ==="
sleep 1

ARGS=("$@")
DMD_NAME="" # DMD A or B selection
for ((i=0; i<${#ARGS[@]}; i++)); do
    case "${ARGS[i]}" in
        --dmd)
            if [[ $((i+1)) -lt ${#ARGS[@]} ]]; then
                DMD_NAME="${ARGS[i+1]}"
            fi
            ;;
        --dmd=*)
            DMD_NAME="${ARGS[i]#--dmd=}"
            ;;
    esac
done

dmd_parse_dmd_config_arg "$@"

MONITOR_INDEX=0
if [ -n "$DMD_NAME" ]; then
    DP_OUTPUT="$(dmd_config_field "$SCRIPT_DIR" "$DMD_NAME" xrandr_output "${DMD_CONFIG_FIELD_ARGS[@]}")"
    MONITOR_FROM_CONFIG="$(dmd_config_field "$SCRIPT_DIR" "$DMD_NAME" glfw_monitor_index "${DMD_CONFIG_FIELD_ARGS[@]}")"
    if [ -n "$MONITOR_FROM_CONFIG" ]; then
        MONITOR_INDEX="$MONITOR_FROM_CONFIG"
    fi
    if [ -z "$DP_OUTPUT" ]; then
        echo "[ERROR] DMD $DMD_NAME has no xrandr_output configured."
        echo "[ERROR] Set xrandr_output in dmd_devices.json before using --dmd so USB and DisplayPort mapping is explicit."
        exit 1
    fi
    dmd_x11_require_connected "$DP_OUTPUT" "DMD $DMD_NAME"
else
    # Single-DMD compatibility path: auto-detect the first connected DisplayPort output.
    DP_OUTPUT="$(dmd_x11_first_connected_output)"
    if [ -z "$DP_OUTPUT" ]; then
        echo "[ERROR] No connected display output found via xrandr!"
        exit 1
    fi
fi
echo "Detected display output: $DP_OUTPUT"

# Define and apply the custom "RAW" modeline.
# Why: DLPC900 sequencer demands the DP source frame rate to match expected
# Video Pattern Mode timing very tightly. CEA-861 1080p60 standard is
# nominally 60Hz but actually 60.019 Hz (148.5 MHz / (2200*1125)). The
# DLPC900 firmware treats anything other than ~60.000 Hz as a sync mismatch
# and latches the forced-swap abort flag (hw 0x08) on every start_pattern_display(2).
#
# Pixel clock 138.6528 MHz gives 138_652_800 / (2080 * 1111) = 60.0000 Hz EXACT.
# Non-standard pclk also prevents the NVIDIA driver from falling back to
# YCbCr 4:2:2 chroma subsampling (which would corrupt our RGB->bitplane pack).
dmd_x11_define_raw_modes "$DP_OUTPUT"

dmd_parse_hz_arg 60 "$@"
TARGET_MODE="$(dmd_x11_target_mode_for_hz "$DMD_TARGET_HZ")"
echo "Applying custom modeline: $TARGET_MODE"
dmd_x11_apply_single_mode "$DP_OUTPUT" "$TARGET_MODE"

# Force NVIDIA to output uncompressed RGB 4:4:4 + disable dithering.
# Belt-and-suspenders on top of the non-standard pclk trick above.
dmd_x11_force_single_rgb "$DP_OUTPUT" "$TARGET_MODE"

sleep 1

# Verify the mode actually took effect.
echo "--- xrandr verification ---"
xrandr --query 2>/dev/null | grep -A 1 "^$DP_OUTPUT" | head -3

echo "=== Launching dmdcontrol single run ==="
dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol single run --monitor "$MONITOR_INDEX" "$@"
