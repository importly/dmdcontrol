#!/bin/bash
# run_dmd.sh
# Automates the sequence of waking up the DisplayPort receiver on the DLPC900 
# and launching the X11 pattern generator

echo "=== DLPC900 Initialization & DP Wake ==="
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

/usr/bin/python3 "$SCRIPT_DIR/wake_dp.py"
if [ $? -ne 0 ]; then
    echo "Error: wake_dp.py failed to run. Check USB connection to DLPC900."
    exit 1
fi

echo "Waiting 6 seconds for Xorg and GPU to detect the DP hotplug event..."
sleep 6

echo "=== Launching Pattern Engine (via xinitrc_dmd.sh wrapper) ==="
# The xinitrc wrapper handles: fixed 1920x1080@60 mode set -> python launch
# Forward CLI arguments to main.py (only --hz 60 is supported)
chmod +x "$SCRIPT_DIR/xinitrc_dmd.sh"
echo 'REDACTED' | sudo -S xinit "$SCRIPT_DIR/xinitrc_dmd.sh" "$@" -- :0 vt1
