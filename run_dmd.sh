#!/bin/bash
# run_dmd.sh
# Automates the sequence of waking up the DisplayPort receiver on the DLPC900 
# and launching the X11 pattern generator
set -e

echo "=== DLPC900 Initialization & DP Wake ==="
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

/usr/bin/python3 "$SCRIPT_DIR/wake_dp.py" "$@"
if [ $? -ne 0 ]; then
    echo "Error: wake_dp.py failed to run. Check USB connection to DLPC900."
    exit 1
fi

echo "Waiting 6 seconds for Xorg and GPU to detect the DP hotplug event..."
sleep 6

echo "=== Launching Pattern Engine (via xinitrc_dmd.sh wrapper) ==="
# The xinitrc wrapper handles: fixed 1920x1080 mode set -> python launch
chmod +x "$SCRIPT_DIR/xinitrc_dmd.sh"
PASS_FILE="$SCRIPT_DIR/.env_pass"
if [ ! -f "$PASS_FILE" ]; then
    echo "Error: $PASS_FILE not found. Create it with: echo 'YOUR_PASSWORD' > $PASS_FILE && chmod 600 $PASS_FILE"
    exit 1
fi
sudo -S xinit "$SCRIPT_DIR/xinitrc_dmd.sh" "$@" -- :0 vt1 < "$PASS_FILE"
