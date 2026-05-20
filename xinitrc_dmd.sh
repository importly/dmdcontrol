#!/bin/bash
# xinitrc_dmd.sh
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "=== xinitrc_dmd: Configuring display for NVIDIA ==="
sleep 1

# Auto-detect the connected DisplayPort output name
DP_OUTPUT=$(xrandr 2>/dev/null | grep ' connected' | grep -oE '^[A-Za-z0-9\-]+' | head -n1)
if [ -z "$DP_OUTPUT" ]; then
    echo "[ERROR] No connected display output found via xrandr!"
    exit 1
fi
echo "Detected display output: $DP_OUTPUT"

# 1. Define and apply the custom "RAW" modeline.
# Why: DLPC900 sequencer demands the DP source frame rate to match expected
# Video Pattern Mode timing very tightly. CEA-861 1080p60 standard is
# nominally 60Hz but actually 60.019 Hz (148.5 MHz / (2200*1125)). The
# DLPC900 firmware treats anything other than ~60.000 Hz as a sync mismatch
# and latches the forced-swap abort flag (hw 0x08) on every start_pattern_display(2).
#
# Pixel clock 138.6528 MHz gives 138_652_800 / (2080 * 1111) = 60.0000 Hz EXACT.
# Non-standard pclk also prevents the NVIDIA driver from falling back to
# YCbCr 4:2:2 chroma subsampling (which would corrupt our RGB->bitplane pack).
MODE_60="1920x1080_60_RAW"
# Errors are NOT silenced - if NVIDIA rejects the custom modeline (because
# /etc/X11/xorg.conf.d/20-nvidia-dlpc.conf is missing or ModeValidation isn't
# disabled), we need to see the failure rather than silently fall through to
# CEA-861 standard timing which causes DLPC900 forced-swap abort.
xrandr --newmode "$MODE_60" 138.6528 1920 1968 2000 2080 1080 1083 1088 1111 +hsync -vsync || echo "[WARN] --newmode $MODE_60 failed (likely already exists - check /etc/X11/xorg.conf.d/20-nvidia-dlpc.conf)"
xrandr --addmode "$DP_OUTPUT" "$MODE_60" || echo "[WARN] --addmode $MODE_60 on $DP_OUTPUT failed"

# Optional: 120 Hz custom mode if --hz 120 is requested upstream.
MODE_120="1920x1080_120_RAW"
xrandr --newmode "$MODE_120" 311.50 1920 1968 2000 2080 1080 1083 1088 1248 +hsync -vsync || echo "[WARN] --newmode $MODE_120 failed"
xrandr --addmode "$DP_OUTPUT" "$MODE_120" || echo "[WARN] --addmode $MODE_120 on $DP_OUTPUT failed"

# Pick the right mode based on --hz argument (defaults to 60).
HZ=60
ARGS=("$@")
for ((i=0; i<${#ARGS[@]}; i++)); do
    if [[ "${ARGS[i]}" == "--hz" && $((i+1)) -lt ${#ARGS[@]} ]]; then
        HZ="${ARGS[i+1]}"
    fi
done

if [[ "$HZ" == "120" ]]; then
    TARGET_MODE="$MODE_120"
else
    TARGET_MODE="$MODE_60"
fi
echo "Applying custom modeline: $TARGET_MODE"
# Two valid paths to apply $TARGET_MODE:
#   (a) xrandr --output ... --mode <name>  - works on nouveau (RandR mode list path)
#   (b) NVIDIA MetaMode baked into /etc/X11/xorg.conf.d/20-nvidia-dlpc.conf - the only
#       path that works with the NVIDIA proprietary driver, because NVIDIA exposes
#       custom modes via the MetaModes API, not RandR's per-output mode list. xrandr
#       returns "cannot find mode" by name even when Xorg.log confirms the mode is
#       already on the wire.
# So: try xrandr first (covers nouveau and any future driver swap), and if it fails
# fall back to validating the NVIDIA MetaMode state. Only abort if neither path applied.
if xrandr --output "$DP_OUTPUT" --mode "$TARGET_MODE" 2>/dev/null; then
    echo "[OK] xrandr applied $TARGET_MODE on $DP_OUTPUT."
else
    echo "[INFO] xrandr cannot switch by mode name (expected on NVIDIA proprietary)."
    echo "[INFO] Validating NVIDIA MetaMode state..."
    CURRENT_MM="$(nvidia-settings -q CurrentMetaMode -t 2>/dev/null || true)"
    if echo "$CURRENT_MM" | grep -q "$TARGET_MODE"; then
        echo "[OK] NVIDIA MetaMode active: $TARGET_MODE (via xorg.conf.d/20-nvidia-dlpc.conf)."
    else
        echo "[ERROR] Neither xrandr nor NVIDIA MetaMode reports $TARGET_MODE active."
        echo "[ERROR] Current MetaMode: ${CURRENT_MM:-<unavailable>}"
        echo "[ERROR] DLPC900 needs exactly 60.000 Hz (138.6528 MHz pclk). CEA-861 60Hz (60.019 Hz) will cause forced-swap abort."
        echo "[ERROR] Verify /etc/X11/xorg.conf.d/20-nvidia-dlpc.conf MetaModes line includes \"$TARGET_MODE +0+0\"."
        exit 1
    fi
fi

# 2. Force NVIDIA to output uncompressed RGB 4:4:4 + disable dithering.
# Belt-and-suspenders on top of the non-standard pclk trick above.
nvidia-settings -a "CurrentMetaMode=${DP_OUTPUT}: ${TARGET_MODE} +0+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}" 2>/dev/null || true
nvidia-settings -a "Dithering=0" 2>/dev/null || true

# Some Xrandr properties also matter on certain drivers (no-op on NVIDIA, harmless).
xrandr --output "$DP_OUTPUT" --set "Broadcast RGB" "Full" 2>/dev/null || true
xrandr --output "$DP_OUTPUT" --set "max bpc" 8 2>/dev/null || true

sleep 1

# Verify the mode actually took effect.
echo "--- xrandr verification ---"
xrandr --query 2>/dev/null | grep -A 1 "^$DP_OUTPUT" | head -3

echo "=== Launching main.py ==="
exec env PYTHONPATH=/home/main/.local/lib/python3.14/site-packages \
    /usr/bin/python3 "$SCRIPT_DIR/main.py" --monitor 0 "$@"