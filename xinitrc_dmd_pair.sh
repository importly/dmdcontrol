#!/bin/bash
# xinitrc_dmd_pair.sh
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "=== xinitrc_dmd_pair: Configuring one spanning X screen ==="
sleep 1

ARGS=("$@")
DMD_CONFIG=""
TARGET_HZ=""
for ((i=0; i<${#ARGS[@]}; i++)); do
    case "${ARGS[i]}" in
        --dmd-config)
            if [[ $((i+1)) -lt ${#ARGS[@]} ]]; then
                DMD_CONFIG="${ARGS[i+1]}"
            fi
            ;;
        --dmd-config=*)
            DMD_CONFIG="${ARGS[i]#--dmd-config=}"
            ;;
        --hz)
            if [[ $((i+1)) -lt ${#ARGS[@]} ]]; then
                TARGET_HZ="${ARGS[i+1]}"
            fi
            ;;
        --hz=*)
            TARGET_HZ="${ARGS[i]#--hz=}"
            ;;
    esac
done

CONFIG_ARGS=()
if [ -n "$DMD_CONFIG" ]; then
    CONFIG_ARGS=(--config "$DMD_CONFIG")
fi

A_OUTPUT="$(/usr/bin/python3 "$SCRIPT_DIR/dmd_config.py" --dmd A "${CONFIG_ARGS[@]}" --field xrandr_output)"
B_OUTPUT="$(/usr/bin/python3 "$SCRIPT_DIR/dmd_config.py" --dmd B "${CONFIG_ARGS[@]}" --field xrandr_output)"
A_HZ="$(/usr/bin/python3 "$SCRIPT_DIR/dmd_config.py" --dmd A "${CONFIG_ARGS[@]}" --field target_hz)"
B_HZ="$(/usr/bin/python3 "$SCRIPT_DIR/dmd_config.py" --dmd B "${CONFIG_ARGS[@]}" --field target_hz)"

if [ -z "$A_OUTPUT" ] || [ -z "$B_OUTPUT" ]; then
    echo "[ERROR] DMD A and B must both define xrandr_output in dmd_devices.json."
    exit 1
fi
if [ -z "$TARGET_HZ" ]; then
    if [ -n "$A_HZ" ] && [ -n "$B_HZ" ] && [ "$A_HZ" != "$B_HZ" ]; then
        echo "[ERROR] DMD A and B target_hz values differ ($A_HZ vs $B_HZ). Pass --hz explicitly or fix dmd_devices.json."
        exit 1
    fi
    TARGET_HZ="${A_HZ:-${B_HZ:-60}}"
fi

if ! xrandr --query 2>/dev/null | grep -q "^$B_OUTPUT connected"; then
    echo "[ERROR] Configured B output '$B_OUTPUT' is not connected."
    xrandr --query 2>/dev/null | grep ' connected' || true
    exit 1
fi
if ! xrandr --query 2>/dev/null | grep -q "^$A_OUTPUT connected"; then
    echo "[ERROR] Configured A output '$A_OUTPUT' is not connected."
    xrandr --query 2>/dev/null | grep ' connected' || true
    exit 1
fi

echo "Pair outputs: B=$B_OUTPUT at +0+0, A=$A_OUTPUT at +1920+0"

MODE_60="1920x1080_60_RAW"
xrandr --newmode "$MODE_60" 138.6528 1920 1968 2000 2080 1080 1083 1088 1111 +hsync -vsync || echo "[WARN] --newmode $MODE_60 failed"
xrandr --addmode "$B_OUTPUT" "$MODE_60" || echo "[WARN] --addmode $MODE_60 on $B_OUTPUT failed"
xrandr --addmode "$A_OUTPUT" "$MODE_60" || echo "[WARN] --addmode $MODE_60 on $A_OUTPUT failed"

MODE_120="1920x1080_120_RAW"
xrandr --newmode "$MODE_120" 311.50 1920 1968 2000 2080 1080 1083 1088 1248 +hsync -vsync || echo "[WARN] --newmode $MODE_120 failed"
xrandr --addmode "$B_OUTPUT" "$MODE_120" || echo "[WARN] --addmode $MODE_120 on $B_OUTPUT failed"
xrandr --addmode "$A_OUTPUT" "$MODE_120" || echo "[WARN] --addmode $MODE_120 on $A_OUTPUT failed"

if [ "$TARGET_HZ" = "120" ]; then
    TARGET_MODE="$MODE_120"
else
    TARGET_MODE="$MODE_60"
fi

echo "Applying paired custom modeline: $TARGET_MODE"
if xrandr --output "$B_OUTPUT" --mode "$TARGET_MODE" --pos 0x0 --primary \
          --output "$A_OUTPUT" --mode "$TARGET_MODE" --pos 1920x0 2>/dev/null; then
    echo "[OK] xrandr applied paired $TARGET_MODE layout."
else
    echo "[INFO] xrandr cannot switch by mode name (expected on NVIDIA proprietary)."
fi

META_MODE="${B_OUTPUT}: ${TARGET_MODE} +0+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}, ${A_OUTPUT}: ${TARGET_MODE} +1920+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}"
nvidia-settings -a "CurrentMetaMode=${META_MODE}" 2>/dev/null || true
nvidia-settings -a "Dithering=0" 2>/dev/null || true

CURRENT_MM="$(nvidia-settings -q CurrentMetaMode -t 2>/dev/null || true)"
if echo "$CURRENT_MM" | grep -q "$B_OUTPUT" \
    && echo "$CURRENT_MM" | grep -q "$A_OUTPUT" \
    && echo "$CURRENT_MM" | grep -q "$TARGET_MODE" \
    && echo "$CURRENT_MM" | grep -q "+1920+0"; then
    echo "[OK] NVIDIA CurrentMetaMode includes paired layout."
else
    echo "[WARN] NVIDIA CurrentMetaMode did not confirm the paired custom MetaMode."
    echo "[WARN] CurrentMetaMode: ${CURRENT_MM:-<unavailable>}"
fi

echo "--- xrandr verification ---"
xrandr --query

if ! xrandr --query | grep -q "Screen 0: current 3840 x 1080"; then
    echo "[ERROR] X screen is not 3840x1080."
    exit 1
fi
if ! xrandr --query | grep -q "^$B_OUTPUT connected primary 1920x1080+0+0"; then
    echo "[ERROR] B output is not primary at 1920x1080+0+0."
    exit 1
fi
if ! xrandr --query | grep -q "^$A_OUTPUT connected 1920x1080+1920+0"; then
    echo "[ERROR] A output is not at 1920x1080+1920+0."
    exit 1
fi

echo "=== Launching main_pair.py ==="
exec env PYTHONPATH=/home/main/.local/lib/python3.14/site-packages \
    /usr/bin/python3 "$SCRIPT_DIR/main_pair.py" "$@"
