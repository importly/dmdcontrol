#!/bin/bash
# run_dmd.sh
# Automates the sequence of waking up the DisplayPort receiver on the DLPC900 
# and launching the X11 pattern generator
set -e

echo "=== DLPC900 Initialization & DP Wake ==="
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/dmd_shell_common.sh"

dmd_wake_with_args "$SCRIPT_DIR" "$@"

dmd_wait_for_hotplug "Xorg and GPU to detect the DP hotplug event"

echo "=== Launching Pattern Engine (via xinitrc_dmd.sh wrapper) ==="
# The xinitrc wrapper handles: fixed 1920x1080 mode set -> python launch
dmd_run_xinit "$SCRIPT_DIR" "$SCRIPT_DIR/xinitrc_dmd.sh" "$@"
