#!/bin/bash
# xinitrc_dmd.sh
# Wrapper script that runs INSIDE the X session started by xinit.
# It forces precise xrandr video timings before launching main.py.
#
# Usage (called from run_dmd.sh):
#   xinit ./xinitrc_dmd.sh [main.py args...] -- :0 vt1

set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Parse hz from args without modifying $@
HZ=60
# Save arguments in an array to iterate over them safely
ARGS=("$@")
for ((i=0; i<${#ARGS[@]}; i++)); do
    if [[ "${ARGS[i]}" == "--hz" && $((i+1)) -lt ${#ARGS[@]} ]]; then
        HZ="${ARGS[i+1]}"
        break
    fi
done

echo "=== xinitrc_dmd: Configuring display for fixed ${HZ}Hz ==="

# ── Wait for X to be fully ready ──
sleep 1

# ── Auto-detect the connected DisplayPort output name ──
# nouveau names it DP-1, DP-2, etc. We grab the first "connected" DP output.
DP_OUTPUT=$(xrandr 2>/dev/null | grep ' connected' | grep -oE '^[A-Za-z0-9\-]+' | head -n1)
if [ -z "$DP_OUTPUT" ]; then
    echo "[ERROR] No connected display output found via xrandr!"
    echo "xrandr output:"
    xrandr 2>&1 || true
    sleep 10
    exit 1
fi
echo "Detected display output: $DP_OUTPUT"

# ── Print current display state for diagnostics ──
echo "--- Current xrandr properties ---"
xrandr --prop 2>&1 | head -50
echo "---"

# ── Force RGB Full Range & Disable Dithering ──
echo "Attempting to force Full RGB Range and disable dithering on $DP_OUTPUT..."

# Intel / AMD common property
xrandr --output "$DP_OUTPUT" --set "Broadcast RGB" "Full" 2>/dev/null || true
# AMD specific dithering
xrandr --output "$DP_OUTPUT" --set "dither" "off" 2>/dev/null || true
# Nouveau specific dithering
xrandr --output "$DP_OUTPUT" --set "dithering mode" "off" 2>/dev/null || true
xrandr --output "$DP_OUTPUT" --set "dithering depth" "8 bpc" 2>/dev/null || true
# Color range (some AMD/Intel drivers)
xrandr --output "$DP_OUTPUT" --set "color range" "Full" 2>/dev/null || true

# ── Define and force a custom modeline to break YCbCr detection ──
# To force the GPU to send raw RGB 4:4:4 instead of compressed YCbCr 4:2:2,
# we use a slightly non-standard pixel clock. This prevents the driver from 
# matching it to a "Standard TV Mode" in its EDID database.
if [ "$HZ" = "120" ]; then
    MODE_NAME="1920x1080_120_RAW"
    xrandr --newmode "$MODE_NAME" 311.50 1920 1968 2000 2080 1080 1083 1088 1248 +hsync -vsync 2>/dev/null || true
else
    MODE_NAME="1920x1080_60_RAW"
    # CVT-R 1920x1080 @ 60Hz reduced blanking, but tweaked pixel clock (138.50 -> 138.51)
    xrandr --newmode "$MODE_NAME" 138.51 1920 1968 2000 2080 1080 1083 1088 1111 +hsync -vsync 2>/dev/null || true
fi

echo "Adding mode $MODE_NAME to output $DP_OUTPUT..."
xrandr --addmode "$DP_OUTPUT" "$MODE_NAME" 2>/dev/null || true
xrandr --output "$DP_OUTPUT" --mode "$MODE_NAME" 2>&1 || {
    echo "[WARNING] Failed to set mode $MODE_NAME. Trying standard 1920x1080..."
    xrandr --output "$DP_OUTPUT" --mode "1920x1080" 2>&1 || {
        echo "[ERROR] Could not set any 1920x1080 mode. Continuing with default..."
    }
}

# Apply dithering disable AGAIN after setting mode (some drivers reset it on mode change)
xrandr --output "$DP_OUTPUT" --set "dithering mode" "off" 2>/dev/null || true
xrandr --output "$DP_OUTPUT" --set "dithering depth" "8 bpc" 2>/dev/null || true
xrandr --output "$DP_OUTPUT" --set "Broadcast RGB" "Full" 2>/dev/null || true
xrandr --output "$DP_OUTPUT" --set "color range" "Full" 2>/dev/null || true
xrandr --output "$DP_OUTPUT" --set "dither" "off" 2>/dev/null || true

# ── Wait for the mode switch to stabilize ──
sleep 1

# ── Print final display state ──
echo "--- xrandr state after mode set ---"
xrandr --prop | grep -A 15 "$DP_OUTPUT connected" 2>&1 || true
echo "---"

# ── Launch the pattern engine ──
echo "=== Launching main.py ==="
# Notice we pass the original arguments intact, so main.py gets --hz if supplied
exec env PYTHONPATH=/home/main/.local/lib/python3.14/site-packages \
    /usr/bin/python3 "$SCRIPT_DIR/main.py" --monitor 0 "$@"
