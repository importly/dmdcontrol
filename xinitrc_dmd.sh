#!/bin/bash
# xinitrc_dmd.sh
# Wrapper script that runs INSIDE the X session started by xinit.
# It forces precise xrandr video timings before launching main.py.
#
# Usage (called from run_dmd.sh):
#   xinit ./xinitrc_dmd.sh [main.py args...] -- :0 vt1

set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "=== xinitrc_dmd: Configuring display for fixed 60Hz ==="

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
echo "--- Current xrandr state ---"
xrandr --query 2>&1 | head -30
echo "---"

# ── Define and force the precise 60Hz modeline ──
MODE_NAME="1920x1080_60"
# CVT-R 1920x1080 @ 60Hz reduced blanking
xrandr --newmode "$MODE_NAME" 138.50 1920 1968 2000 2080 1080 1083 1088 1111 +hsync -vsync 2>/dev/null || true

echo "Adding mode $MODE_NAME to output $DP_OUTPUT..."
xrandr --addmode "$DP_OUTPUT" "$MODE_NAME" 2>/dev/null || true
xrandr --output "$DP_OUTPUT" --mode "$MODE_NAME" 2>&1 || {
    echo "[WARNING] Failed to set mode $MODE_NAME. Trying standard 1920x1080..."
    # Fallback: try to set the output to any available 1920x1080 mode
    xrandr --output "$DP_OUTPUT" --mode "1920x1080" 2>&1 || {
        echo "[ERROR] Could not set any 1920x1080 mode. Continuing with default..."
    }
}

# ── Wait for the mode switch to stabilize ──
sleep 1

# ── Print final display state ──
echo "--- xrandr state after mode set ---"
xrandr --query 2>&1 | head -20
echo "---"

# ── Launch the pattern engine ──
echo "=== Launching main.py ==="
exec env PYTHONPATH=/home/main/.local/lib/python3.14/site-packages \
    /usr/bin/python3 "$SCRIPT_DIR/main.py" --monitor 0 "$@"
